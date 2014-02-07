#!/usr/local/bin/python

import logging
log = logging.getLogger('SSHClient')

from twisted.internet.protocol import ReconnectingClientFactory
#from twisted.conch.ssh import connection
from twisted.internet import reactor
from twisted.internet import defer
from twisted.python import failure
from twisted.conch.ssh import filetransfer
import fnmatch
import stat

# Local Code
from transport import SSHTransport
from connection import Connection
from auth import PasswordAuth
from channel import CommandChannel
from channel import SFTPChannel


class SSHClient(ReconnectingClientFactory):

    # the underlying transport/protocol
    protocol = SSHTransport
    maxDelay = 2

    def __init__(self, options, reactor=reactor):
        self.options = options
        self.reactor = reactor

        # Defaults
        self.connectionTimeout = 10
        self.timeout = 3  # Timeout for the commands

        # Runtime
        # --------------------------------------------------------------
        self.connector = None

        # Deferred that fires when the client is created
        self.dClient = defer.Deferred()

        # Deferred that fires when the transport connection is ready.
        self.dTransport = defer.Deferred()

        # Deferred that fires if the connection is ready
        self.dConnected = defer.Deferred()

        self.runningDeferreds = []  # Handle closing these on connection
                                    # lost or failed.

        # Deferred that fires if the connection is ready
        self.dSftpclient = None

        # Initialize the deferreds
        self.resetConnection()

    def buildProtocol(self, addr):
        log.debug('Building a new protocol')
        self.resetDelay()
        client = self.protocol()
        client.factory = self
        self.dClient.callback(client)
        return client

    def _startConnection(self, data, dConnected):
        'returns a dConnected deferred to indicate success'
        def _requestService(client):
            client.requestService(PasswordAuth(self.options,
                                               self.connection,
                                               self))

        log.debug('creating dConnected deferred')
        self.connection = Connection(self, self.dConnected)
        self.dClient.addCallback(_requestService)

    def _startConnectionFailed(self, data):
        '''Catch transport errors'''
        pass
        #log.debug('In _startConnectionFailed')

    def _ebdClient(self, data):
        '''Catch dclient errorbacks.  We could log these
        but the client should just reconnect'''
        pass

    def resetConnection(self, reason=None):
        dClient, self.dClient = self.dClient, defer.Deferred()
        dTransport, self.dTransport = self.dTransport, defer.Deferred()
        dConnected, self.dConnected = self.dConnected, defer.Deferred()
        dSftpclient, self.dSftpclient = self.dSftpclient, None

        # if reason we had a problem and should err the dClient
        if not dClient.called and reason:
            dClient.errback(reason)

        # Send errors to any inflight command
        # deferreds that havent been called
        if reason:
            for d in self.runningDeferreds:
                if not d.called:
                    log.debug("resetting %s with Reason:%s" % (d, reason))
                    d.errback(reason)

        self.dTransport.addCallback(self._startConnection,
                                    self.dConnected)

        self.dTransport.addErrback(self._startConnectionFailed)
        self.dClient.addErrback(self._ebdClient)

    def clientConnectionLost(self, connector, reason):
        log.debug("Lost connection to %s" % (reason))
        self.resetConnection(reason)
        ReconnectingClientFactory.clientConnectionLost(self,
                                                       connector,
                                                       reason)

    def clientConnectionFailed(self, connector, reason):
        log.debug("Connection failed to %s" % (reason))
        self.resetConnection(reason)
        ReconnectingClientFactory.clientConnectionFailed(self,
                                                         connector,
                                                         reason)

    def connect(self):
        t = self.connectionTimeout
        self.connector = self.reactor.connectTCP(self.options['hostname'],
                                                 self.options['port'], self,
                                                 timeout=t)

    def disconnect(self):
        self.stopTrying()
        connector, self.connector = self.connector, None
        if connector:
            if hasattr(connector, 'transport') and connector.transport:
                connector.transport.loseConnection()

      #  return self.dConnected
    def _cleanupRunningDeferreds(self, data, deferred):
        # callback/errback to remove fired deferreds from the
        # runningDeferreds list
        if deferred in self.runningDeferreds:
            self.runningDeferreds.remove(deferred)
        return data

    def trackDeferred(self, deferred):
        # Keep track of which deferreds are running from the user in
        # case there is an error and we need to log it.
        self.runningDeferreds.append(deferred)

        # Cleanup the running deferreds when done
        deferred.addBoth(self._cleanupRunningDeferreds, deferred)

    # Begin Helper callbacks
    # ------------------------------------------------------------------
    def _cbRun(self, connection, command, result, timeout=None):
        log.debug('entered _cbRun')
        channel = CommandChannel(command, result, conn=connection,
                                 timeout=timeout)
        connection.openChannel(channel)
        return connection

    def _cbftpclient(self, connection, client, timeout):
        log.debug('Creating file transfer client')
        channel = SFTPChannel(client, connection=connection)
        connection.openChannel(channel)
        return connection

    def SftpClientConnect(self, timeout=None):
        timeout = timeout or self.timeout
        if not self.dSftpclient:
            d = defer.Deferred()
            log.debug('Starting to create dSftpclient')
            self.dConnected.addCallback(self._cbftpclient, d, timeout)
            self.dSftpclient = d
        return d

    def _cbreadfile(self, files, l, directory, glob):
        'Recursively scan the directories'
        if not isinstance(files, failure.Failure):
            if glob:
                l.extend([f for f in files if fnmatch.fnmatch(f[0], glob)])
            else:
                l.extend(files)
            d = directory.read()
            d.addBoth(self._cbreadfile, l, directory, glob)
            return d
        else:
            reason = files
            reason.trap(EOFError)
            directory.close()
            return l

    def _cbopenlist(self, directory, glob):
        files = []
        d = directory.read()
        d.addBoth(self._cbreadfile, files, directory, glob)
        return d

    def _remoteglob(self, client, path):
        d = client.openDirectory(path)
        d.addCallback(self._cbopenlist, '')
        return d

    def _cbdone(self, result, callback):
        if isinstance(result, failure.Failure):
            callback.errback(result)
        else:
            callback.callback(result)

    def _cbls(self, client, path, result):
        log.debug('calling _remoteglob')
        d = self._remoteglob(client, path)
        d.addBoth(self._cbdone, result)
        return client

    def _cbln(self, client, source, destination, result):
        client.makeLink(source, destination).addBoth(self._cbdone, result)
        return client

    def _cbchown(self, client, path, owner, result):
        owner = int(owner)
        d = client.getAttrs(path)
        d.addCallback(self._cbsetusrgrp, client, path, owner=owner)
        d.addBoth(self._cbdone, result)
        return d

    def _cbgetopenfile(self, remote, local):
        d = remote.getAttrs()
        d.addCallback(self._cbGetFileSize, remote, local)
        return d

    def _cbgetdone(self, d, remote, local):
        log.debug('entering cbgetdone')
        'Close the remote and local file handles'
        local.close()
        remote.close()
        return

    def _cbGetFileSize(self, attrs, remote, local):
        if not stat.S_ISREG(attrs['permissions']):
            remote.close()
            local.close()
            return "Can't get non-regular file: %s" % remote.name
        remote.size = attrs['size']
        remote.total = 0.0
        bufSize = int(self.options['buffersize'] or 32768)
        chunks = []
        d = self._cbgetread('', remote, local, chunks, 0, bufSize, remote.size)
        d.addCallback(self._cbgetdone, remote, local)
        return d

    def _getNextChunk(self, chunks):
        end = 0
        for chunk in chunks:
            try:
                if chunk[1] == 'eof':
                    return
            except Exception:
                pass
            if end == 'eof':
                return  # nothing more to get
            if end != chunk[0]:
                i = chunks.index(chunk)
                chunks.insert(i, (end, chunk[0]))
                return (end, chunk[0] - end)
            end = chunk[1]
        bufSize = int(self.options['buffersize'] or 32768)
        chunks.append((end, end + bufSize))
        return (end, bufSize)

    def _cbgetread(self, data, remote, local, chunks, start,
                   bufSize, remoteSize):
        if data and isinstance(data, failure.Failure):
            log.debug('get read err: %s' % data)
            reason = data
            reason.trap(EOFError)
            i = chunks.index((start, start + bufSize))
            del chunks[i]
            chunks.insert(i, (start, 'eof'))
        elif data:
            log.debug('get read data: %i' % len(data))
            local.seek(start)
            local.write(data)
            if len(data) != bufSize:
                log.debug('got less than we asked for: %i < %i' %
                         (len(data), bufSize))
                i = chunks.index((start, start + bufSize))
                del chunks[i]
                chunks.insert(i, (start, start + len(data)))
            remote.total += len(data)
        chunk = self._getNextChunk(chunks)
        if not chunk:
            return
        else:
            start, length = chunk
        log.debug('asking for %i -> %i' % (start, start+length))
        d = remote.readChunk(start, length)
        d.addBoth(self._cbgetread, remote, local, chunks, start,
                  length, remote.size)
        return d

    def _ebcloselocalfile(self, f, local):
        'Close an open localfile on error'
        local.close()
        return f

    def _cbget(self, client, source, destination, result):
        lf = open(destination, 'w')
        lf.seek(0)
        flags = filetransfer.FXF_READ
        d = client.openFile(source, flags, {})
        d.addCallback(self._cbgetopenfile, lf)
        d.addErrback(self._ebcloselocalfile, lf)
        d.addBoth(self._cbdone, result)
        return d

    def _cbputfile(self, remote, local):
        log.debug('entering cbputfile')
        chunks = []
        d = self._cbputwrite(None, remote, local, chunks)
        d.addCallback(self._cbputdone, remote, local)
        return d

    def _cbputwrite(self, ignored, remote, local, chunks):

        chunk = self._getNextChunk(chunks)
        log.debug('entering cbputwrite')
        log.debug(chunk)
        start, size = chunk
        local.seek(start)
        data = local.read(size)
        if data:
            d = remote.writeChunk(start, data)
            d.addCallback(self._cbputwrite, remote, local, chunks)
            return d
        else:
            return

    def _cbputdone(self, d, remote, local):
        log.debug('entering cbputdone')
        'Close the remote and local file handles'
        local.close()
        remote.close()
        return d

    def _cbsetusrgrp(self, attrs, client, path, owner=None, group=None):
        new = {}
        new['uid'] = (owner is not None) and owner or attrs['uid']
        new['gid'] = (group is not None) and group or attrs['gid']
        d = client.setAttrs(path, new)
        return d

    def _cbchgrp(self, client, path, group, result):
        group = int(group)
        d = client.getAttrs(path)
        d.addCallback(self._cbsetusrgrp, client, path, group=group)
        d.addBoth(self._cbdone, result)
        return d

    def _cbchmod(self, client, path, perms, result):
        log.debug('in cbchmod')
        perms = int(perms, 8)
        d = client.setAttrs(path, {'permissions': perms})
        d.addBoth(self._cbdone, result)
        return d

    def _cbmkdir(self, client, directory, result):
        d = client.makeDirectory(directory, {})
        d.addBoth(self._cbdone, result)
        return d

    def _cbrename(self, client, old, new, result):
        d = client.renameFile(old, new)
        d.addBoth(self._cbdone, result)
        return d

    def _cbrm(self, client, path, result):
        d = client.removeFile(path)
        d.addBoth(self._cbdone, result)
        return d

    def _cbrmdir(self, client, directory, result):
        d = client.removeDirectory(directory)
        d.addBoth(self._cbdone, result)
        return d

    def _cbput(self, client, source, destination, result):
        def done(result, callback):
            if isinstance(result, failure.Failure):
                callback.errback(result)
            else:
                callback.callback(result)

        lf = file(source, 'r')
        flags = filetransfer.FXF_WRITE | \
            filetransfer.FXF_CREAT | \
            filetransfer.FXF_TRUNC
        d = client.openFile(destination, flags, {})
        d.addCallback(self._cbputfile, lf)
        d.addErrback(self._ebcloselocalfile, lf)
        d.addBoth(self._cbdone, result)
        return d

    # End Callbacks
    # ------------------------------------------------------------------
    def chgrp(self, path, group, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbchgrp, path, group, d)
        return d

    def chmod(self, path, perms, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbchmod, path, perms, d)
        return d

    def chown(self, path, owner, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbchown, path, owner, d)
        return d

    def get(self, source, destination, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbget, source, destination, d)
        return d

    def ln(self, source, destination, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbln, source, destination, d)
        return d

    def ls(self, path, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbls, path, d)
        return d

    def mkdir(self, directory, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbmkdir, directory, d)
        return d

    def rename(self, old, new, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbrename, old, new, d)
        return d

    def rm(self, path, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbrm, path, d)
        return d

    def rmdir(self, directory, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbrmdir, directory, d)
        return d

    def run(self, command, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)
        self.dConnected.addCallback(self._cbRun, command, d, timeout)
        return d

    def put(self, source, destination, timeout=None):
        timeout = timeout or self.timeout
        d = defer.Deferred()
        self.trackDeferred(d)

        self.SftpClientConnect()
        self.dSftpclient.addCallback(self._cbput, source, destination, d)
        return d










