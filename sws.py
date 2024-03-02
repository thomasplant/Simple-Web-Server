#!/usr/bin/env python3
import select
import socket
from datetime import datetime, timedelta
import queue 
import sys
import re
from os.path import exists

#Closes a socket
def close_socket(s) -> None:
    client[s].closed = True

    if s in outputs: outputs.remove(s)
    if s in inputs: inputs.remove(s)
    
    del client[s]
    s.close()

#This checks to see if the port number and address is present on launch
def check_input() -> None:
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        print("Invalid Adress or Port \nPlease use format: \npython3 sws.py {IP Adress} {Port Number} \n")
        sys.exit()
        
        
class connection:

    def __init__(self, conn, addr) -> None:
        self.message_queue = queue.Queue()
        self.last_activity = datetime.now()
        self.valid_GET = False
        self.filename = ""
        self.valid_file = False
        self.persistent = False
        self.conn = conn
        self.addr = addr
        self.request = ""
        self.closed = False
        self.message_buf = ""

    #Prints log to consol
    def log(self, response) -> None:
        now = datetime.now()
        now = now.astimezone()
        print(now.strftime("%a %b %d %X %Z %Y: ") + str(self.addr[0]) + ":" + str(self.addr[1]) + " " + self.request + "; " + response )

    #Checks filename from request and stores it
    def findfile(self,line) -> None:
        path = line.split(" ")
        if path[1] == "/":
            self.filename = "./index.html" 
        else:
            self.filename = "." + path[1]

        if exists(self.filename):
            self.valid_file = True

    #Sent when request is invalid
    def return_400(self) -> None:
        self.conn.send("HTTP/1.0 400 Bad Request\r\nConnection: close\r\n\r\n".encode())
        self.log("HTTP/1.0 400 Bad Request")
        close_socket(self.conn)
        
    #Sent when valid and file is present
    def return200(self) ->None:
        try:
            f = open(self.filename)
        except:
            self.valid_file = False
            self.return404()

        #Excecutes if the file is opened
        else:
            response_file = f.read()
            f.close()
            if self.persistent:
                self.conn.send(("HTTP/1.0 200 OK\r\nConnection: keep-alive\r\n\r\n" + response_file).encode())
            else:
                self.conn.send(("HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n" + response_file).encode())
                close_socket(self.conn)

            self.log("HTTP/1.0 200 OK")

    #Sent when file not found but valid request
    def return404(self) ->None:
        if self.persistent:
            self.conn.send("HTTP/1.0 404 Not Found\r\nConnection: keep-alive\r\n\r\n".encode())
        else:
            self.conn.send("HTTP/1.0 404 Not Found\r\nConnection: close\r\n\r\n".encode())
            close_socket(self.conn)

        self.log("HTTP/1.0 404 Not Found")


    #Parses incoming data and determines what variables need to be called or if a request is needed
    def parse(self) -> None:

        while self.message_queue.qsize() > 0:
            requests = self.message_queue.get_nowait()
            
            #Handles if Carrage returns are used and then splits up each line if multiple were passed
            enters = len(re.findall('\n', requests))
            #This checks if some of the message didn't make it over TCP, if so wait for it.
            if enters == 0:
                self.message_buf = requests
            else:
                if not self.message_buf == "":
                    requests = self.message_buf + requests
                    self.message_buf = ""
                
            requests = requests.replace("\r", "")
            requests = requests.split("\n") 
            
            for i, line in enumerate(requests):
                if i >= enters or self.closed == True:
                    break

                #Looking for a Header
                if not self.valid_GET:
                    if not (line == ""):
                        self.request = line
                        if bool(re.match(r"GET /.* HTTP/1\.0 *", line)):
                            self.valid_GET = True
                            self.findfile(line)
                        else:
                            self.return_400()

                else:
                    #Valid header, looking for connection: keep-alive or enter
                    if bool(re.match(r"connection: *keep-alive *", line, re.IGNORECASE)):
                        self.persistent = True
                    elif line == "":
                        if self.valid_file:
                            self.return200()
                        else:
                            self.return404()

                        self.valid_GET = False
                        self.persistent = False

            


#-----Main----
#check if user entered valid ip and port
check_input()

#set up the server
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
server.setblocking(False)
server.bind((sys.argv[1], int(sys.argv[2])))
server.listen(5)

#SETTING UP OUR VARIABLES
inputs = [server]
outputs = []
client = {} #where we will store the connection class
timeout = timedelta(seconds=30) 

while inputs:

    #Server waits until one of these gets modified or timeout reached
    readable, writable, exceptional = select.select(inputs, outputs, inputs, 6)
        
    for s in readable:

        #Check if new connection
        if s is server:
        
            conn, addr = s.accept()
            conn.setblocking(0)
            inputs.append(conn)
            client[conn] = connection(conn, addr)


        else:
            #Socket has data ready to read 
            data = s.recv(1024)
            if data:
                client[s].message_queue.put(data.decode())
                client[s].last_activity = datetime.now()
                if s not in outputs:
                    outputs.append(s)


    for s in writable:
        #Data sent to process                    
        client[s].parse()
        if s in outputs: outputs.remove(s)


    for s in exceptional:
        close_socket(s)
    
    #Checking for timeout
    for s in inputs:
        if s is not server:
            if s not in exceptional and s not in writable and not s in readable:
                if datetime.now() >= client[s].last_activity + timeout:
                    close_socket(s)

