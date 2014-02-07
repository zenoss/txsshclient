from twisted.conch.ssh import channel
from twisted.conch.ssh import common
from twisted.conch.error import ConchError
from twisted.internet import reactor
import struct
from twisted.conch.ssh.common import NS
from twisted.conch.ssh.filetransfer import FileTransferClient
from twisted.internet.error import TimeoutError
from twisted.python import failure

import logging
log = logging.getLogger('channel')


class CommandChannel(channel.SSHChannel):
    name = "session"

    def __init__(self, command, result, timeout=None,
                 reactor=reactor, *args, **kwargs):
        """
        @param command: command to run
        @type command: string
        @param result: deferred to callback (exit, stdout, stderr)
                       or errback (code, value) with
        @type result: Deferred
        @param conn: connection to create the channel on
        @type conn: Twisted connection object
        """
        channel.SSHChannel.__init__(self, *args, **kwargs)
        self.command = command
        self.result = result
        self.timeout = timeout
        self.reactor = reactor
        self.out = ''
        self.err = ''
        self.exit = 1
        self.timeoutId = None
        log.debug('Command Channel initialized')

    def openFailed(self, reason):
        if isinstance(reason, ConchError):
            res = (reason.data, reason.value)
        else:
            res = (reason.code, reason.desc)

        self.result.errback(res)
        channel.SSHChannel.openFailed(self, reason)

    def timeoutCancel(self):
        if self.timeoutId:
            self.timeoutId.cancel()

    def startTimer(self):
        if self.timeout:
            log.debug('starting timer with %s timeout' % self.timeout)
            self.timeoutId = self.reactor.callLater(self.timeout,
                                                    self._timeoutCalled)

    def _timeoutCalled(self):
        log.debug('timeout triggered')
        if not self.result.called:
            self.result.errback(TimeoutError())
        self.timeoutId = None
        self.loseConnection()

    def channelOpen(self, _):
        self.startTimer()
        log.debug("ChannelOpen: Sending Command \"%s\"" % self.command)
        req = self.conn.sendRequest(self,
                                    "exec",
                                    common.NS(self.command),
                                    wantReply=True)
        req.addCallback(lambda _: self.conn.sendEOF(self))
        return req

    def dataReceived(self, data):
        self.out = self.out + data

    def extReceived(self, dataType, data):
        if dataType == 1:
            self.err = self.err + data

    def request_exit_status(self, data):
        self.exit = struct.unpack('>L', data)[0]

        log.debug('Sending results back to the callback')
        self.result.callback((self.exit, self.out, self.err))

    def eofReceived(self):
        if self.result is not None:
            self.timeoutCancel()


class SFTPChannel(channel.SSHChannel):
    name = 'session'

    def __init__(self, clientHandle, connection,
                 timeout=None, reactor=reactor, *args, **kwargs):
        channel.SSHChannel.__init__(self, *args, **kwargs)
        self.clientHandle = clientHandle
        self.conn = connection
        self.timeout = timeout
        self.reactor = reactor
        self.timeoutId = None
        log.debug('SFTP Channel initialized')

    def timeoutCancel(self):
        if self.timeoutId:
            self.timeoutId.cancel()

    def startTimer(self):
        if self.timeout:
            log.debug('starting timer with %s timeout' % self.timeout)
            self.timeoutId = self.reactor.callLater(self.timeout,
                                                    self._timeoutCalled)

    def _timeoutCalled(self):
        self.clientHandle.errback(TimeoutError())
        self.timeoutId = None
        self.loseConnection()

    def channelOpen(self, whatever):
        log.debug('SFTP Channel opened')
        d = self.conn.sendRequest(
            self, 'subsystem', NS('sftp'), wantReply=True)
        d.addCallbacks(self._cbSFTP)

    def _cbSFTP(self, result):
        self.startTimer()
        client = FileTransferClient()
        client.makeConnection(self)
        self.dataReceived = client.dataReceived
        log.debug('setting clientHandle to be %s' % client)
        self.clientHandle.callback(client)
        self.timeoutCancel()
        log.debug('Created SFTP Client')

    def openFailed(self, reason):
        if isinstance(reason, ConchError):
            res = (reason.data, reason.value)
        else:
            res = (reason.code, reason.desc)

        self.clientHandle.errback(res)
        channel.SSHChannel.openFailed(self, reason)
