from test_common import SSHServer, ServerProtocol, ClientProtocol
from sshclient.test5 import SSHClient
from twisted.trial.unittest import TestCase
from twisted.internet import reactor, defer
import getpass
import logging
log = logging.getLogger('test_functional')

import tempfile
import os
import shutil

def touch(path):
    with open(path, 'a'):
        os.utime(path, None)


class IPV4FunctionalBaseTestCase(TestCase):
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
        self.client.factory.protocol = ClientProtocol
        self.client.connect()
        #self.client.factory.protocol.onConnectionLost = defer.Deferred()

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
        return defer.gatherResults([d,
                                    client.factory.onConnectionLost,
                                    server.onConnectionLost])

    def test_run_command(self):

        d = self.client.run('echo hi')

        def got_hi(data):
            log.debug('Got Data %s' % (data,))
            self.assertEquals(data,  (1, 'hi\n', ''))
            return data

        d.addCallback(got_hi)
        return d

    @defer.inlineCallbacks
    def test_lsdir(self):
        try:
            test_file = 'test_ls_dir'
            sandbox = tempfile.mkdtemp()
            testfile = '/'.join([sandbox, test_file])
            touch(testfile)
            d = yield self.client.ls(sandbox)

            self.assertEquals(d[0][0], test_file)
            defer.returnValue(d)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_mkdir(self):
        try:
            sandbox = tempfile.mkdtemp()
            test_dir = 'tmpMkdir'
            directory = '/'.join([sandbox, test_dir])
            result = yield self.client.mkdir(directory)
            self.assertEquals(result[0], 'mkdir succeeded')
            self.assertTrue(os.path.isdir(directory))
            defer.returnValue(result)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_rmdir(self):
        try:
            sandbox = tempfile.mkdtemp()
            test_dir = 'tmpRmdir'
            directory = '/'.join([sandbox, test_dir])
            os.mkdir(directory)
            result = yield self.client.rmdir(directory)
            self.assertEquals(result[0], 'rmdir succeeded')
            self.assertFalse(os.path.exists(directory))
            defer.returnValue(result)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_rename(self):
        try:
            original_filename = 'test_rename'
            destination_filename = 'test_rename_changed'
            sandbox = tempfile.mkdtemp()
            original_path = '/'.join([sandbox, original_filename])
            destination_path = '/'.join([sandbox, destination_filename])
            touch(original_path)

            result = yield self.client.rename(original_path,
                                              destination_path)
            self.assertEquals(result[0], 'rename succeeded')
            self.assertFalse(os.path.exists(original_path))
            self.assertTrue(os.path.exists(destination_path))
            defer.returnValue(result)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_ln(self):
        try:
            original_filename = 'test_ln'
            destination_filename = 'test_ln_destination'
            sandbox = tempfile.mkdtemp()
            original_path = '/'.join([sandbox, original_filename])
            destination_path = '/'.join([sandbox, destination_filename])
            touch(original_path)
            result = yield self.client.ln(destination_path, original_path)

            self.assertEquals(result[0], 'symlink succeeded')
            self.assertTrue(os.path.isfile(original_path))
            self.assertTrue(os.path.islink(destination_path))
            defer.returnValue(result)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_rm(self):
        try:
            original_filename = 'test_rm_file'
            sandbox = tempfile.mkdtemp()
            original_path = '/'.join([sandbox, original_filename])
            touch(original_path)

            result = yield self.client.rm(original_path)

            self.assertEquals(result[0], 'remove succeeded')
            self.assertFalse(os.path.exists(original_path))
            defer.returnValue(result)
        finally:
            shutil.rmtree(sandbox)

    @defer.inlineCallbacks
    def test_put(self):
        try:
            source_data = 'This was my sourcefile...'
            source_filename = 'test_source_file'
            destination_filename = 'test_destination_file'

            source_sandbox = tempfile.mkdtemp()
            destination_sandbox = tempfile.mkdtemp()

            source_path = '/'.join([source_sandbox, source_filename])
            destination_path = '/'.join([destination_sandbox,
                                         destination_filename])
            open(source_path, 'w').write(source_data)

            result = yield self.client.put(source_path, destination_path)
            self.assertTrue(os.path.isfile(source_path))
            self.assertTrue(os.path.isfile(destination_path))
            self.assertEqual(source_data,
                             open(destination_path, 'r').read())
            defer.returnValue(result)
        finally:
            shutil.rmtree(source_sandbox)
            shutil.rmtree(destination_sandbox)

    @defer.inlineCallbacks
    def test_get(self):
        try:
            source_data = 'This was my sourcefile...'
            source_filename = 'test_source_file'
            destination_filename = 'test_destination_file'

            source_sandbox = tempfile.mkdtemp()
            destination_sandbox = tempfile.mkdtemp()

            source_path = '/'.join([source_sandbox, source_filename])
            destination_path = '/'.join([destination_sandbox,
                                         destination_filename])
            open(source_path, 'w').write(source_data)

            result = yield self.client.get(source_path, destination_path)
            self.assertTrue(os.path.isfile(source_path))
            self.assertTrue(os.path.isfile(destination_path))
            self.assertEqual(source_data,
                             open(destination_path, 'r').read())
            defer.returnValue(result)
        finally:
            shutil.rmtree(source_sandbox)
            shutil.rmtree(destination_sandbox)



    # TODO
    # chown, chgrp, chmod


    #reactor.callWhenRunning(run)


    #reactor.callWhenRunning(put)
    #reactor.callWhenRunning(get)


class IPV6FunctionalBaseTestCase(TestCase):
    def setUp(self):
        self.hostname = '::1'
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
        self.client.factory.protocol = ClientProtocol
        self.client.connect()
        #self.client.factory.protocol.onConnectionLost = defer.Deferred()

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
        return defer.gatherResults([d,
                                    client.factory.onConnectionLost,
                                    server.onConnectionLost])

    def test_run_command(self):

        d = self.client.run('echo hi')

        def got_hi(data):
            log.debug('Got Data %s' % (data,))
            self.assertEquals(data,  (1, 'hi\n', ''))
            return data

        d.addCallback(got_hi)
        #d = defer.Deferred()
        #d.callback('done')
        return d
