from main import *
from pprint import pprint, pformat
import xml.etree.ElementTree

class EvalBot(Session):
	last_eval = None
	remote_id_message_map = {}

	def on_message(self, message, d):
		if message.text.startswith("@"):
			divider = "#"*10
			command = message.text.split(divider)[0]
			command = ''.join(xml.etree.ElementTree.fromstring("<z>" + command + "</z>").itertext())
			if command.endswith("\n"):
				command = command[:-1]

			print("command:", command)

			if command == self.last_eval:
				return
			self.last_eval = command

			try:
				if command.startswith("@eval:"):
					output = str(eval(command[6:]))
				elif command.startswith("@pprint:"):
					output = pformat(eval(command[8:]))
				else:
					output = "invalid command"
			except Exception as e:
				output = str(e)

			print("out:", output)

			output = '<pre raw_pre="{code}" raw_post="{code}">' + command + '\n' + divider + '\n' + output +'</pre>'

			if message.editable:
				message.edit(output)
			else:
				if message.id in self.remote_id_message_map:
					self.remote_id_message_map[message.id].edit(output)
				else:
					m = OwnMessage(self.session)
					m.fromMessage(message)
					print(m)
					m.send()
					m.edit(output)
					self.remote_id_message_map[message.id] = m

