import socket
import select
import ssl
import multiprocessing, threading
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from urlparse import urlparse, urljoin
from httplib import HTTPResponse, BadStatusLine
from StringIO import StringIO
from urlparse import urlparse



ip = "127.0.0.1"
port = 8080
buff_size = 4096
nl = '\r\n'

class MismatchedHost(Exception):
    pass

class ConnectionThread(threading.Thread):
    def __init__(self,socket):
        threading.Thread.__init__(self)
        self.insocket = socket
        self.killed = False
    
    def kill(self):
        self.killed = True
    
    def format_request(self, request):    
        headers = request.lower().split()
        host, port, path = self.decode_url(headers[1])   
        if host != self.host or port != self.port:
            raise MismatchedHost("Host or port does not match up")
        request = request.replace(headers[1],path)
        return request
        
    def decode_url(self,url):
        doubleSlash = url.find("//")
        if doubleSlash != -1:
            url = url[doubleSlash+2:]
            
        colon = url.find(":")
        slash = url.find("/")
        if slash != -1 and colon > slash:
            colon = -1
        question = url.find("?")
        if colon == -1:
            port = 80
            if slash != -1:
                host = url[:slash]
                path = url[slash:]
            elif question != -1:
                host = url[:question]
                path = url[question:]
            else:
                host = url
                path = "/"
        else:
            host = url[:colon]
            if slash != -1:
                port = url[colon+1:slash]
                path = url[slash:]
            elif question != -1:
                port = url[colon+1:question]
                path = url[question:]
            else:
                port = url[colon+1:]
                path = "/"
        
        return host, port, path
    
    def get_host_and_port(self, request):
        headers = request.lower().split()
        if "host:" in headers:
            host = headers[headers.index("host:")+1].strip()
        # TODO: See if "hosts" are ever different
        if host:
            _, port, _ = self.decode_url(headers[1])
        else:
            host, port, _ = self.decode_url(headers[1])
        return host, int(port)
    
    def method_type(self, request):
        methods = ["get","head","post","put","delete","trace","connect"]
        for method in methods:
            if request.lower().startswith(method):
                return method
        # TODO: Exception
        print "No method found!"
        return None
    
    def run(self):
        self.new_connection() 

    def new_connection(self, request=""):
        if request == "":
            
            while(True):
                r,w,x = select.select([self.insocket],[],[],0)
                if len(r) > 0:
                    request += self.insocket.recv(2**22)
                    # TODO: We're ignoring the possibility of the 
                    # break occuring on the message body.
                    if request[-4:] == "\r\n\r\n":
                        break

        # Now that we have the request
        # Let's open up the socket
        print request
        
        # TODO: make sure it all works
        # catch exceptions and close nice
        self.method = self.method_type(request)
        self.host, self.port = self.get_host_and_port(request)
        self.outsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


        try:
            self.outsocket = socket.create_connection((self.host, self.port))
        except socket.timeout:
            print "End connection timed out"
            outsocket.close()
            return
        except socket.error:
            print "End connection timed out"
            outsocket.close()
            return
        except socket.gaierror:
            print "End connection timed out"
            outsocket.close()
            return
        
        
        if self.method == "get" or self.method == "post":
            self.get(request)
        elif self.method == "connect":
            self.connect()
        else:
            # TODO: throw exception
            print "Unsupported method"
            self.end()
        return
        
    def get(self, request):
 
        # Format and pass along the initial request
        request = self.format_request(request)
        self.outsocket.sendall(request)
 
        # Wait for request
        while(True):
            r,w,x = select.select([self.insocket, self.outsocket],[],[],0)
            if self.insocket in r:
                request = self.insocket.recv(buff_size)
                if request == "":
                    print "Got end message from browser"
                    self.kill()
                else:
                    try:
                        request = self.format_request(request)
                    except MismatchedHost:
                        print "Host changed. Getting new end socket"
                        self.insocket.sendall("")
                        self.kill()                
                self.outsocket.sendall(request)
            if self.outsocket in r: 
                httpRes = HTTPResponse(self.outsocket)
                response = ""
                try:
                    httpRes.begin()
                    
                    headers = str(httpRes.msg)
                    content = httpRes.read()
                    
                    if headers.find("Transfer-Encoding: chunked") != -1:
                        headers = headers.replace("Transfer-Encoding: chunked\r\n", "")
                        headers += "Content Length: " + str(len(content)) + "\r\n"
                    
                    if httpRes.version == 10:
                        response += "HTTP/1.0 "
                    elif httpRes.version == 11:
                        response += "HTTP/1.1 "
                    response += str(httpRes.status) + " " + str(httpRes.reason) + nl
                    response += headers + nl
                    response += content
                    #print response
                except BadStatusLine:
                    self.kill()
                self.insocket.sendall(response)
                self.kill()
                #'''
            if self.killed:
                self.end()
                return           
           
    def connect(self):   
        self.insocket.sendall("HTTP/1.1 200 Connection established\r\n\r\n")

        while(True):
            r,w,x = select.select([self.insocket, self.outsocket],[],[],0)
            if self.insocket in r:
                message = self.insocket.recv(buff_size)
                self.outsocket.sendall(message)
                if message == "":
                    print "dead"
                    self.kill()
            if self.outsocket in r:
                message = self.outsocket.recv(buff_size)
                self.insocket.sendall(message)
                if message == "":
                    print "dead"
                    self.kill()
            if self.killed:
                self.end()
                return

        
        

    def end(self):
        try:
            self.insocket.shutdown(socket.SHUT_RD)
        except:
            print "shutdown problem"
            pass
        try:
            self.outsocket.close()
        except:
            pass
        return
def main():
    threads = []

    try:
        insocket = socket.socket(socket.AF_INET,type=socket.SOCK_STREAM)
        insocket.bind((ip, port))
        insocket.listen(10)
    
        while(True):
            r,w,x = select.select([insocket],[],[],0)
            if len(r) > 0:
                remote, addr = insocket.accept()
                newthread = ConnectionThread(remote)
                threads.append(newthread)
                newthread.start()
    except KeyboardInterrupt:
        print "Keyboard Interrupt in main"
        insocket.close()
        for thread in threads:
            thread.kill()
        return   
       

if __name__ == "__main__":
    main()