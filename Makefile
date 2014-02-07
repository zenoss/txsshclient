check:
	find . -name *.pyc -print -exec rm {} \;
	PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_functional.IPV4FunctionalBaseTestCase.test_lsdir_no_dir
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_functional.IPV4FunctionalBaseTestCase.test_chown
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_functional.IPV4FunctionalBaseTestCase.test_chgrp
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_functional.IPV4FunctionalBaseTestCase.test_chmod
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test
	#PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test.test_timeouts.IPV4TimeoutTestCase.test_lsdir
