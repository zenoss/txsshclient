UNITTESTS ?= test

check:
	find . -name *.pyc -print -exec rm {} \;
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test
	PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_errors.IPV4FunctionalReconnectTestCase.test_run_command

