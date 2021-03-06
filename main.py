import requests
import uuid
import re
import time
import getpass
import json
import random
import arrow
from pprint import pprint, pformat

API_BASE_URL = "https://api.skype.com"
MY_USER = API_BASE_URL + "/users/self/"


def generate_session_id():
	session_id = hex(int(time.time()*1000))[-8:]
	hexlist = "0123456789abcdef"
	for c in "-xxxx-4xxx-yxxx-xxxxxxxxxxxx":
		if c == "x":
			session_id += random.choice(hexlist)
		elif c == "y":
			session_id += random.choice(hexlist[8:12])
		else:
			session_id += c
		#print(len(session_id), session_id)
	assert len(session_id) == 8 + 5*3 + 1 + 12
	return session_id


class Session:

	def __init__(self, username, password=None):
		self.username = username
		self.password = password

	def sign_in(self):
		username = self.username
		password = self.password
		if not username:
			username = input("Username: ")
		if not password:
			password = getpass.getpass()

		print("getting formdata")
		login_page=requests.get("https://login.skype.com/login?client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com")
		pie = re.search('<input.*?name="pie".*?value="(.*?)".*?/>', login_page.content.decode("ascii", "ignore")).group(1)
		etm = re.search('<input.*?name="etm".*?value="(.*?)".*?/>', login_page.content.decode("ascii", "ignore")).group(1)

		print(pie)
		print(etm)

		session = requests.Session()
		self.session = session

		print("sending name&pw")
		r = session.post("https://login.skype.com/login?client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com", data={
			"username": username,
			"password": password,
			"pie": pie,
			"etm": etm,
			"client_id": 578134,
			"js_time": time.time()
		})

		if not r.ok:
			raise RuntimeError(r.reason)
		if not "skype-session" in r.cookies:
			raise RuntimeError("invalid login")
		print("OK")


		print("getting X-Skypetoken")
		login = session.get("https://login.skype.com/login/silent?response_type=postmessage&client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com%2Fde%2F&state=silentloginsdk_1434643089469&_accept=1.0&_nc=1434643089469")
		skypeToken = re.search('\\\\"skypetoken\\\\":\\\\"(.*?)\\\\"', login.content.decode("ascii", "ignore")).group(1)

		session.headers.update({"X-Skypetoken": skypeToken})

		print("token auth")
		session.post("https://api.asm.skype.com/v1/skypetokenauth", data={"skypetoken": skypeToken})

		session.headers.update({"Authentication": "skypetoken="+session.cookies["skypetoken_asm"]})
		print("getting RegistrationToken")
		r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints", data=json.dumps({}))
		session.headers.pop("Authentication")
		for s in r.headers["Set-RegistrationToken"].split("; "):
			k, v = s.split("=")[0], "=".join(s.split("=")[1:])
			print(k, v)
			if k == "registrationToken":
				registrationToken = v
				session.headers.update({"RegistrationToken": s})
			elif k == "endpointId":
				print("endpointId:", v)
			elif k == "expires":
				pass
			else:
				raise RuntimeError(k + ": " + str(v))

		print("eligibility_check...")
		if not self.eligibility_check():
			raise RuntimeError("Session not eligible")

		self.sessionId = generate_session_id()
		print("sessionId:", self.sessionId)
		print("session-ping...")
		if not self.session_ping():
			raise RuntimeError("session-ping failed")

		print("creating endpoints")
		session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints", data=json.dumps({}))

		print("requesting subscriptions")
		d = {
			"channelType": "httpLongPoll",
			"interestedResources": [
				"/v1/users/ME/conversations/ALL/properties",
				"/v1/users/ME/conversations/ALL/messages",
				"/v1/users/ME/contacts/ALL",
				"/v1/threads/ALL"
			],
			"template": "raw"
		}
		session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints/SELF/subscriptions", json.dumps(d))

		return session


	def create_endpoint(self):
		self.session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints", data=json.dumps({}))

	def put_endpoint(self, sid):
		r = self.session.put("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints/%7B" + sid + "%7D")
		pprint(vars(r))
		return r.json()

	def on_message(self, message, d):
		pass

	def parse_update(self, d):
		print("#{id}; {type}; {resourceType}".format(**d))
		resource = d["resource"]
		#pprint(resource)
		t = d["resourceType"]
		if t == "UserPresence":
			print(resource["selfLink"].split("/")[-3], "is", resource["status"])
		elif t == "EndpointPresence":
			user = resource["selfLink"].split("/")[-5]
			capabilities = resource["publicInfo"]["capabilities"].split(" | ")
			capabilities = [c for c in capabilities if c != '']
			epname = resource["privateInfo"]["epname"] # ...
			print(user, "is capable of", capabilities, "on", epname)
		elif t == "NewMessage":
			if resource['messagetype'] in ['Control/Typing', 'Control/ClearTyping']:
				user = resource["from"].split("/")[-1]
				print(user, "is typing...")
			elif resource['messagetype'] == 'RichText':
				m = Message.fromResource(resource, self)
				print(m)
				self.on_message(m, resource)
		elif t == "ConversationUpdate":
			m = Message.fromResource(resource['lastMessage'])
			after = (arrow.now() - arrow.get(resource['lastMessage']['originalarrivaltime'])).total_seconds()
			print("'{}' from '{}' in '{}' read after {} seconds".format(m.text, m.sender, m.conversation, after))
		else:
			print("Unknown resourceType!")
			pprint(resource)

	def listen(self):
		while True:
			res = self.poll()
			if not res:
				continue
			for d in res["eventMessages"]:
				self.parse_update(d)

	def poll(self, since=None):
		if not since:
			since = time.time()*1000000

		self.session.headers["ContextId"] = "tcid="+str(since)
		r = self.session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints/SELF/subscriptions/0/poll")
		self.session.headers.pop("ContextId")

		if not r.ok:
			print("poll not ok")

		if len(r.content) > 0:
			return r.json()
		else:
			return None

	def profile(self):
		r = self.session.get(MY_USER+'profile')
		return r.json()

	def session_ping(self):
		r = self.session.post("https://web.skype.com/api/v1/session-ping", data={"sessionId": self.sessionId})
		pprint(vars(r))
		return r.ok

	def eligibility_check(self):
		r = self.session.get("https://web.skype.com/api/v2/eligibility-check")
		print(r)
		print(vars(r))
		return r.ok

	def contacts(self):
		r = self.session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/contacts", data=json.dumps({"contacts": []}))
		pprint(vars(r))
		return r.json()

	def contacts2(self, user):
		r = self.session.get("https://contacts.skype.com/contacts/v1/users/" + user + "/contacts?filter=contacts[?(@.type=%22skype%22%20or%20@.type=%22msn%22)]")
		pprint(vars(r))
		return r.json()

	def messages(self, user):
		r = self.session.get("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + user + "/messages?startTime=0&pageSize=30&view=msnp24Equivalent&targetType=Passport|Skype|Lync|Thread")
		pprint(vars(r))
		return r.json()

class Message:
	editable = False
	text = None
	sender = None
	conversation = None
	id = None
	edited_id = None
	sent = True

	def fromMessage(self, m):
		self.text = m.text
		self.sender = m.sender
		self.conversation = m.conversation
		self.id = m.id
		self.edited_id = m.edited_id
	
	@classmethod
	def fromResource(cls, resource, session=None):
		m = None
		if session:
			if resource["from"].split("/")[-1] == "8:"+session.username:
				m = OwnMessage(session.session)

		if not m:
			m = Message()

		m.text = resource["content"]
		m.conversation = resource["conversationLink"].split("/")[-1]
		m.sender = resource["from"].split("/")[-1]

		print("New message from:", m.sender, "in", m.conversation)
		print(m.text)
		if "clientmessageid" in resource:
			m.id = resource["clientmessageid"]
			m.edited_id = None
		else:
			m.edited_id = resource["skypeeditedid"]
			m.id = resource["id"]
		return m

	def __repr__(self):
		return "<Message(conversation={}, sender={}, text={}, id={}>".format(self.conversation, self.sender, self.text, self.id)


class OwnMessage(Message):
	def __init__(self, session):
		self.session = session
		self.editable = True

	def send(self):
		self.id = int(time.time()*1000)
		d = {
			"content": self.text,
			"contenttype": "text",
			"messagetype": "RichText",
			"clientmessageid": self.id
		}
		r = self.session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + self.conversation + "/messages", data=json.dumps(d))
		if r.ok:
			self.sent = True
		return r.ok


	def edit(self, text):
		self.text = text
		d = {
			"content": text,
			"skypeeditedid": self.edited_id if self.edited_id else self.id,
			"contenttype": "text",
			"messagetype": "RichText"
		}

		r = self.session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + self.conversation + "/messages", data=json.dumps(d))
		
		return r.status_code == 201

	def delete(self):
		return self.edit("")

