#!/usr/local/bin/python

import logging
log = logging.getLogger('SSHClient')

from twisted.internet.protocol import ReconnectingClientFactory
#from twisted.conch.ssh import connection
from twisted.internet import reactor
from twisted.internet import defer

# Local Code
from transport import SSHTransport
from connection import Connection
from auth import PasswordAuth
from channel import CommandChannel


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

    def resetConnection(self, reason=None):
        dClient, self.dClient = self.dClient, defer.Deferred()
        dTransport, self.dTransport = self.dTransport, defer.Deferred()
        dConnected, self.dConnected = self.dConnected, defer.Deferred()

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
            if connector.transport:
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

    def _cbRun(self, connection, command, result, timeout=None):
        log.debug('entered _cbRun')
        channel = CommandChannel(command, result, conn=connection, timeout=timeout)
        connection.openChannel(channel)
        return connection

    def run(self, command, timeout=None):
        timeout = timeout or self.timeout
        log.debug('Called run')
        d = defer.Deferred()
        self.trackDeferred(d)
        self.dConnected.addBoth(self._cbRun, command, d, timeout)
        return d







