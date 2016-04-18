# Bitbucket Sync #

Sync all of your repositories between your computer and BitBucket. You might want to backup all of your repositories. Or keep them in sync between your office network and the cloud. Or when you are travelling.

You can use the script either with Buildout or Virtualenv.

## Settings ##

The script uses netrc to store the credentials needed to access Bitbucket API.

Example ``~/.netrc`` file:

    machine bitbucket.org
      login foo
      password bar

## Help ##

    Usage: bbsync [OPTIONS] COMMAND [ARGS]...

    Options:
      --quiet
      --debug
      --config TEXT
      --help         Show this message and exit.

    Commands:
      clear     Remove working area from all directories.
      fetch     Fetch repositories from Bitbucket.
      ghsync    Sync all repos to Github.
      groups    Grant access for group to repository.
      hg2git    Commit identical copy from hg to git.
      show      Shows a list of all repositories in bitbucket
      sync      Sync all repos to Bitbucket.
      tree      Shows a tree of all repositories in bitbucket
      workarea  Sync local workarea to Bitbucket.

