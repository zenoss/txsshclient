from twisted.internet import defer
from twisted.conch.ssh import userauth
import os
import pwd
from pprint import pformat

import logging
log = logging.getLogger('auth')


class SshUserNotSetError(Exception):
    '''Raise a no user exception.'''
    pass


class SshNoPasswordError(Exception):
    '''Raise a no user exception.'''
    pass


class PasswordAuth(userauth.SSHUserAuthClient):
    """Auth Class that gets the password from the factory"""
    #SSHUserAuthClient(self, user, options, *args)
    def __init__(self, options, conn, factory, *args):
        userauth.SSHUserAuthClient.__init__(self, options['user'], conn)
        self.options = options
        self.user = options['user']
        self._sent_password = False
        self._sent_pk = False
        self._sent_kbint = False
        self.factory = factory

        user = str(self.user)
        if user == '':
            log.debug('User not set. Falling back to process user.')

            # From the Python docs about the preferred method of
            # obtaining user name in preference to os.getlogin()
            #  (http://docs.python.org/library/os.html)
            try:
                user = os.environ.get('LOGNAME', pwd.getpwuid(os.getuid())[0])
            except:
                pass

            if user == '':
                message = "User not set and unable to determine from "\
                          "process user."
                raise SshUserNotSetError(message)
        userauth.SSHUserAuthClient.__init__(self, user, conn)

    def getPassword(self, unused=None):
        """
        Return a deferred object of success if there's a password or
        return fail

        @param unused: unused (unused)
        @type unused: string

        @return: Twisted deferred object (defer.succeed or defer.fail)
        @rtype: Twisted deferred object

        """
        # Do not re-send the same credentials if we have already been called.
        if self._sent_password:
            return None

        try:
            password = self._getPassword()
            d = defer.succeed(password)
            self._sent_password = True

        except SshNoPasswordError:
            # NOTE: Return None here - not a defer.fail(). If a failure
            # deferred is returned, then the SSH client will retry until
            # MaxAuthTries is met - which in some SSH server
            # implementations means an infinite number of retries.
            # Returning None here indicates that we don't want to try
            # password authentication because we don't have a username
            # or password.
            d = None
        return d

    def _getPassword(self):
        """
        Get the password. Raise an exception if it is not set.
        """
        if not self.options['password']:
            message = "no password set in options"
            raise SshNoPasswordError(message)
        return self.options['password']

    def getGenericAnswers(self, name, instruction, prompts):
        """
        Called from conch.

        Returns a L{Deferred} with the responses to the prompts.

        @param name: The name of the authentication currently in progress.
        @param instruction: Describes what the authentication wants.
        @param prompts: A list of (prompt, echo) pairs, where prompt is a
        string to display and echo is a boolean indicating whether the
        user's response should be echoed as they type it.
        """

        log.debug('getGenericAnswers name:"%s" instruction:"%s" prompts:%s',
                  name, instruction, pformat(prompts))

        if not prompts:
            # RFC 4256 - In the case that the server sends a `0' num-prompts
            # field in the request message, the client MUST send a response
            # message with a `0' num-responses field to complete the exchange.
            d = defer.succeed([])

        else:
            responses = []
            found_prompt = False
            for prompt, echo in prompts:
                if 'password' in prompt.lower():
                    found_prompt = True
                    try:
                        responses.append(self._getPassword())
                    except SshNoPasswordError:
                        # This shouldn't happen -
                        #      we don't support keyboard interactive
                        # auth unless a password is specified
                        log.debug("getGenericAnswers called with empty"
                                  " password")
            if not found_prompt:
                log.warning('No known prompts: %s', pformat(prompts))
            d = defer.succeed(responses)
        return d
