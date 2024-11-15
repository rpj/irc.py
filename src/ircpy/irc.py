import asyncio
import telnetlib3
import re
import os
import base64
import sys

class Bot:
    def __init__(self,  **kwargs):
        self._events = {}
        self._args = kwargs
        self.use_sasl_auth = os.environ.get("IRCPY_SASL_AUTH")
        global nickname
        global server
        global channel
        global port
        global prefix
        nickname = self._args["nickname"]
        server = self._args["server"]
        channel = self._args["channel"]
        try:
            port = int(self._args["port"])
        except:
            port = 6667
        try:
            prefix = self._args["prefix"]
        except:
            prefix = "!"
    def send_message(self, message):
        self.writer.write(f"PRIVMSG {channel} :{message}\r\n")
    def event(self, func):
        event_name = func.__name__
        if event_name not in self._events:
            self._events[event_name] = []
        self._events[event_name].append(func)
        return func
    async def callevent(self, event, *args):
        try:
            tasks = []
            for handler in self._events[event]:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(*args))
                else:
                    handler(*args)
            if tasks:
                await asyncio.gather(*tasks)
        except:
            pass
    def connect(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._connect())
    async def _connect(self):
        self.reader, self.writer = await telnetlib3.open_connection(
            server, port, encoding='utf-8'
        )

        _og_writer = self.writer.write
        def _writer_wrapper(*args, **kwargs):
            if os.environ.get("IRCPY_DEBUG"):
                sys.stdout.write(f"C>> {args[0]}")
            return _og_writer(*args, **kwargs)
        self.writer.write = _writer_wrapper

        if self.use_sasl_auth:
            self.writer.write("CAP REQ :sasl\r\n")

        self.writer.write(f"NICK {nickname}\r\n")
        self.writer.write(f"USER {nickname} 0 * :{nickname}\r\n")

        nickserv_password = os.environ.get("IRCPY_NICKSERV_PASSWORD")
        if nickserv_password:
            if self.use_sasl_auth:
                self.writer.write("AUTHENTICATE PLAIN\r\n")
            else:
                self.writer.write(f"PRIVMSG NickServ :IDENTIFY {nickserv_password}\r\n")

        if not self.use_sasl_auth:
            self.writer.write(f"JOIN {channel}\r\n")
            await self.callevent("ready", nickname, channel)
        while True:
            line = await self.reader.readline()
            if not line:
                break
            await self.handle_line(line.strip())
    async def handle_line(self, line):
        if os.environ.get("IRCPY_DEBUG"):
            print(f"S>> {line}")

        if self.use_sasl_auth and line.startswith("AUTHENTICATE +"):
            auth_bytes = bytes(f"{nickname}\x00{nickname}\x00{os.environ.get('IRCPY_NICKSERV_PASSWORD')}", "utf-8")
            auth_str = base64.b64encode(auth_bytes).decode("utf-8")
            self.writer.write(f"AUTHENTICATE {auth_str}\r\n")
            self.writer.write(f"CAP END\r\n")

        if self.use_sasl_auth and line.find(":SASL authentication successful") != -1:
            self.writer.write(f"PRIVMSG NickServ :IDENTIFY {os.environ.get('IRCPY_NICKSERV_PASSWORD')}\r\n")
            self.writer.write(f"JOIN {channel}\r\n")
            await self.callevent("ready", nickname, channel)

        if line.startswith("PING"):
            self.writer.write(f"PONG {line.split()[1]}\r\n")

        if "PRIVMSG" in line:
           fullident = line.split('PRIVMSG')[0]
           msg = re.findall(f"(?<={channel.lower()} :).*$", line)
           if msg:
               msg = msg[0]
           user = re.findall("(?<=~).*(?=@)", fullident)
           if user:
               user = user[0]
           if not prefix in line:
               [nick, ident] = fullident[1:].strip().split("!")
               await self.callevent("message_received", msg, user, channel, nick, ident)
           else:
               try:
                   msg_splitted = msg.split(' ')
               except:
                   msg_splitted = msg
               try:
                   cmd = msg_splitted[0].replace(prefix, '')
               except:
                   cmd = msg_splitted
               arguments = []
               for arg in msg_splitted:
                   if prefix in arg:
                       pass
                   else:
                       arguments.append(arg)
               await self.callevent(cmd, arguments, user, channel, msg)
