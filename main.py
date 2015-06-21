import requests
import uuid
import re
import time
import getpass
import json
from pprint import pprint

API_BASE_URL = "https://api.skype.com"
MY_USER = API_BASE_URL + "/users/self/"


def sign_in(username=None, password=None):

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


	return session


def connect(name, pw):
	auth_request = requests.get(MY_USER+"contacts/auth-request")
	return auth_request

def poll(session):
	r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/endpoints/SELF/subscriptions/0/poll")
	print(r, r.content)
	return r

def profile(session):
	r = session.get(MY_USER+'profile')
	return r.json()

def ping(session, sessionid):
	r = requests.post("https://web.skype.com/api/v1/session-ping", params={"sessionId": sessionid})
	return r

def eligibility_check(session):
	r = session.get("https://web.skype.com/api/v2/eligibility-check")
	print(r)
	print(vars(r))
	return r.ok

def contacts(session):
	r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/contacts", data=json.dumps({"contacts": []}))
	pprint(vars(r))
	return r.json()

def contacts2(session, user):
	r = session.get("https://contacts.skype.com/contacts/v1/users/" + user + "/contacts?filter=contacts[?(@.type=%22skype%22%20or%20@.type=%22msn%22)]")
	pprint(vars(r))
	return r.json()

def messages(session, user):
	r = session.get("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + user + "/messages?startTime=0&pageSize=30&view=msnp24Equivalent&targetType=Passport|Skype|Lync|Thread")
	pprint(vars(r))
	return r.json()



class Message:
	def __init__(self, session, to, text, msg_time=None):
		if not msg_time:
			self.id = int(time.time()*1000)
		else:
			self.id = msg_time
		self.session = session
		self.to = to
		self.text = text
		
		d = {
			"content": text,
			"contenttype": "text",
			"messagetype": "RichText",
			"clientmessageid": self.id
		}

		r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + to + "/messages", data=json.dumps(d))
		

	def edit(self, text):
		self.text = text
		return editmessage(self.session, self.to, text, self.id)

	def delete(self):
		return self.edit("")
	
	def __repr__(self):
		return "<Message(to={}, text={}, id={}>".format(self.to, self.text, self.id)


def sendmessage(session, to, text="testtest"):
	#clientmessageid: "1434893657047"
	#content: "testtest"
	#contenttype: "text"
	#messagetype: "RichText"
	d = {
		"content": text,
		"contenttype": "text",
		"messagetype": "RichText",
		"clientmessageid": int(time.time()*1000) 
	}
	print(d["clientmessageid"])
	r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + to + "/messages", data=json.dumps(d))
	pprint(vars(r))
	print(r.status_code == 201)
	rd = r.json()
	rd.update({"clientmessageid": d["clientmessageid"]})
	return rd

def editmessage(session, to, text, message):
	#content: "testtest test"
	#contenttype: "text"
	#messagetype: "RichText"
	#skypeeditedid: "1434893657047"
	d = {
		"content": text,
		"skypeeditedid": message,
		"contenttype": "text",
		"messagetype": "RichText"
	}
	
	r = session.post("https://client-s.gateway.messenger.live.com/v1/users/ME/conversations/" + to + "/messages", data=json.dumps(d))
	pprint(vars(r))
	print(r.status_code == 201)
	return r.json()

def testmsg(session, to):
	
	m1 = Message(session, to=to, text="Nachricht1")
	m2 = Message(session, to=to, text="Nachricht2")
	m3 = Message(session, to=to, text="Zeitreise!", msg_time=int((time.time()-60)*1000))
	time.sleep(5)
	for i in range(1, 10):
		ii = str(i)
		m1.edit("Nachricht 1 Edit #"+ii)
		m2.edit("Nachricht 2 Edit #"+ii)
		m3.edit("Zeitreise!  Edit #"+ii)
		time.sleep(1)
	
	for m in [m1, m2, m3]:
		m.edit(repr(m))
		m.delete()


session = sign_in()

