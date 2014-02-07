check:
	find . -name *.pyc -print -exec rm {} \;
	PYTHONPATH="${PYTHONPATH}:`pwd`/sshclient" trial --temp-directory=/tmp/_trial_tmp sshclient.test
