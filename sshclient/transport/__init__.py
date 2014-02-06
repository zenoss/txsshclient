from twisted.internet import defer
from twisted.conch.ssh import transport

import logging
log = logging.getLogger('SSHTransport')


class SSHTransport(transport.SSHClientTransport):
    def __init__(self):
        log.debug('Initialized the Transport Protocol' )

    def verifyHostKey(self, hostKey, fingerprint):
        log.debug('Verify Host Key')
        return defer.succeed(True)

    def connectionSecure(self):
        log.debug('Transport connectionSecure')

        # We are connected to the otherside.
        self.factory.dTransport.callback(self)
