from test_common import SSHServer, ServerProtocol, ClientProtocol
from sshclient import SSHClient
from twisted.trial.unittest import TestCase
from twisted.internet import reactor, defer
import getpass
import logging
log = logging.getLogger('test_exec')

from twisted.internet.error import ConnectionLost, ConnectError, UserError

import shutil
import tempfile
import logging
#logging.basicConfig(level=logging.DEBUG)
#logging.basicConfig(level=logging.INFO)
#from twisted.python import log as twistedlog
#observer = twistedlog.PythonLoggingObserver()
#observer.start()
log = logging.getLogger('test_errors')

class IPV4FunctionalNoServerTestCase(TestCase):
    def setUp(self):
        self.hostname = '127.0.0.1'
        self.user = getpass.getuser()
        self.password = 'dummyTestPassword'
        self.server = SSHServer()
        self.server.protocol = ServerProtocol

        self.port = reactor.listenTCP(0, self.server, interface=self.hostname)
        self.portnum = self.port.getHost().port

        options = {'hostname': self.hostname,
                   'port': self.portnum+1,
                   'user': self.user,
                   'password': self.password,
                   'buffersize': 32768}

        self.client = SSHClient(options)
        self.client.protocol = ClientProtocol
        self.client.connect()

    def tearDown(self):
        # Shut down the server and client
        port, self.port = self.port, None
        client, self.client = self.client, None
        server, self.server = self.server, None

        # A Deferred for the server listening port
        d = port.stopListening()

        # Tell the client to disconnect and not retry.
        client.disconnect()

        # Wait for the deferred that tell us we disconnected.
        return defer.gatherResults([d])

    def test_run_command_connect_failure(self):
        'test what happens if the server isnt running'
        d = self.client.run('echo hi')
        return self.assertFailure(d, ConnectError)

    def test_ls_connect_failure(self):
        'test what happens if the server isnt running'

        sandbox = tempfile.mkdtemp()
        d = self.client.ls(sandbox)

        def sandbox_cleanup(data):
            shutil.rmtree(sandbox)
            return data
        d.addBoth(sandbox_cleanup)
        return self.assertFailure(d, ConnectError)


class IPV4FunctionalTestCase(TestCase):
    def setUp(self):
        self.hostname = '127.0.0.1'
        self.user = getpass.getuser()
        self.password = 'dummyTestPassword'
        self.server = SSHServer()
        self.server.protocol = ServerProtocol

        self.port = reactor.listenTCP(0, self.server, interface=self.hostname)
        self.portnum = self.port.getHost().port

        options = {'hostname': self.hostname,
                   'port': self.portnum,
                   'user': self.user,
                   'password': self.password,
                   'buffersize': 32768}

        self.client = SSHClient(options)
        self.client.protocol = ClientProtocol
        self.client.connect()

    def tearDown(self):
        # Shut down the server and client
        log.debug('tearing down')
        port, self.port = self.port, None
        client, self.client = self.client, None
        server, self.server = self.server, None

        # A Deferred for the server listening port
        d = port.stopListening()

        # Tell the client to disconnect and not retry.
        client.disconnect()

        return defer.gatherResults([d,
                                    client.onConnectionLost,
                                    server.onConnectionLost])

    def test_run_command(self):

        def server_stop_listening(data):
            sld = self.port.stopListening()
            return sld

        def server_drop_connections(data):
            port, self.port = self.port, None
            server, self.server = self.server, None
            server.protocol.transport.loseConnection()
            return server.onConnectionLost

        def run_command(sld):
            results = self.client.run('echo hi')
            return results

        def test_failure(data):
            return self.assertFailure(data, ConnectionLost)


        def test_success(data):
            self.assertEqual(data, (0, 'hi\n', ''))
            return data

        def start_server(data):
            self.server = SSHServer()
            self.server.protocol = ServerProtocol
            self.port = reactor.listenTCP(self.portnum,
                                          self.server,
                                          interface=self.hostname)
            return self.port

        d = self.client.run('echo hi')
        d.addBoth(test_success)
        d.addCallback(server_stop_listening)
        d.addCallback(server_drop_connections)
        d.addCallback(run_command)
        d.addBoth(test_failure)
        d.addBoth(start_server)
        d.addCallback(run_command)
        d.addBoth(test_success)
        return d





