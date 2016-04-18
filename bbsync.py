
import sys
import os
import os.path
from netrc import netrc
import subprocess
import click
import requests


login, account, password = netrc().authenticators('bitbucket.org')
auth = (login, password)

import ConfigParser
settings = ConfigParser.RawConfigParser()
BASEDIR = os.path.dirname(os.path.abspath(__file__))
settings.read([os.path.join(BASEDIR, 'default.conf')])

DEBUG = False

def repo2slug(repo):
  return repo.replace('/', '-')


def client(method, *args, **kwargs):
  f = getattr(requests, method)
  kwargs['auth'] = auth
#  print repr(args), repr(kwargs)
  res = f(*args, **kwargs)
#  print repr(res), repr(res.content)
  return res.json()

def paged_query(*args, **kwargs):
  """ Compiles paginated query to the API.
  Fetches All objects.
  """
  r = client(*args, **kwargs)
  for o in r['values']:
    yield o
  if 'next' in r:
    while 'next' in r and r['next']:
      r = client('get', r['next'])
      for o in r['values']:
        yield o


def cmd(cmdline):
  if DEBUG: print cmdline; return
  subprocess.call(cmdline, shell=True)

def cmdo(cmdline):
  if DEBUG: print cmdline; return ''
  return subprocess.check_output(cmdline, shell=True)


def create_bitbucket_repo(user, repo, scm='hg'):
  data = {
    'name': repo,
    'scm': scm,
    'is_private': True,
    }
  if DEBUG: print repr(data); return
  try:
    client('post', 'https://bitbucket.org/api/1.0/repositories', data=data)
  except ValueError:
    pass


def group_access_for_repo(user, repo, group_owner, group_slug, privilege='read'):
  data = {
    'accountname': user,
    'repo_slug': repo2slug(repo),
    'group_owner': group_owner,
    'group_slug': group_slug,
  }
  url = 'https://api.bitbucket.org/1.0/group-privileges/{accountname}/{repo_slug}/{group_owner}/{group_slug}'.format(**data)
  if DEBUG: print repr(data), repr(privilege), repr(url); return
  try:
    client('put', url, data=privilege)
  except ValueError:
    pass


def set_post_hooks(user, repo, hooks, from_config=False):
  if from_config:
    global settings
    hooks = list(hooks)
    for k,v in settings.items('hooks'):
      if not v in hooks:
        hooks.append(v)
  api_url = 'https://bitbucket.org/api/1.0/repositories/%s/%s/services/' % (user, repo2slug(repo))
  raw_data = client('get', api_url)
  post_services = []
  for d in raw_data:
    if d['service']['type'] == 'POST':
      post_services.append(d['service']['fields'][0]['value'])
  for url in hooks:
    print 'hook: POST,', url
    if url not in post_services:
      data = {
        'type': 'POST',
        'URL': url,
        }
      try:
        client('post', api_url, data=data)
      except ValueError:
        pass


def bitbucket_repos(user):
  for d in paged_query('get', 'https://bitbucket.org/api/2.0/repositories/%s?pagelen=100'%user):
    o = {}
    o['scm'] = d['scm']
    o['username'] = d['owner']['username']
    o['name'] = d['name']
    o['href'] = d['links']['clone'][1]['href']
    o['dn'] = repo2slug(o['name'])
    yield o


def bitbucket_repo_tree(user):
  t = {}
  for d in bitbucket_repos(user):
    dirs = d['name'].split('/')
    s = t
    for n in dirs:
      if n not in s:
        s[n] = {}
      if n == dirs[-1]:
        s[n] = d
      else:
        s = s[n]
  return t


def sync_repo(scm, directory, user, repo, post_hooks, hooks_from_config):
  slug = repo2slug(repo)
  href = 'ssh://hg@bitbucket.org/%s/%s' % (user, slug)
  create_bitbucket_repo(user, repo, scm)
  set_post_hooks(user, repo, post_hooks, hooks_from_config)
  if scm == 'hg':
    cmd('cd "%s" && hg push -f %s' % (directory, href))
    cmd('cd "%s" && hg pull %s' % (directory, href))
  if scm == 'git':
    cmd('cd "%s" && git push --all -f %s' % (directory, href))
    cmd('cd "%s" && git pull %s' % (directory, href))


@click.group()
@click.option('--quiet', is_flag=True, default=False)
@click.option('--debug', is_flag=True, default=False)
@click.option('--config', default=os.path.expanduser('~/.bbsync.conf'))
@click.pass_context
def cli(ctx, quiet, debug, config):
  global DEBUG
  DEBUG = debug
  ctx.obj = {}
  ctx.obj['VERBOSE'] = not quiet
  global settings
  settings.read(config)


@cli.command()
@click.argument('user')
def show(user):
  """ Shows a list of all repositories in bitbucket
  """
  for d in bitbucket_repos(user):
    print d['dn'], d['href']


@cli.command()
@click.argument('user')
def tree(user):
  """ Shows a tree of all repositories in bitbucket
  """
  from pprint import PrettyPrinter
  P = PrettyPrinter(indent=2)
  P.pprint(bitbucket_repo_tree(user))


@cli.command()
@click.argument('user')
@click.option('--sync', is_flag=True)
@click.option('--clean', is_flag=True)
@click.option('--hook', multiple=True)
@click.option('-h', is_flag=True)
@click.pass_context
def fetch(ctx, user, sync, clean, hook, h):
  """ Fetch repositories from Bitbucket.

  Uses the current directory as destination.
  Does pull if local repository already exists, otherwise clone.

  You need to provide your Bitbucket username as parameter.

  You can also do push with --sync.

  For example: Your username in Bitbucket is "asdf".
  You want all new reporitories and changes to existing repositories
  fetched from Bitbucket and to push all local changes.
  The command is then:

    bbsync fetch --sync asdf
  """
  for r in bitbucket_repos(user):
    if ctx.obj['VERBOSE']: print u'Fetching %s to %s' % (r['href'], r['dn'])
    set_post_hooks(user, r['dn'], hook, h)
    if r['scm'] == 'hg':
      if os.path.isdir(os.path.join(r['dn'], '.hg')):
        cmd('cd "%s" && hg pull %s' % (r['dn'], r['href']))
        if clean:
          cmd('cd "%s" && hg up -C -r null && hg clean --all' % r['dn'])
      else:
        cmd('hg clone -U %s "%s"' % (r['href'], r['dn']))
      if sync:
        cmd('cd "%s" && hg push -f %s' % (r['dn'], r['href']))
    elif r['scm'] == 'git':
      d = '%s.git' % r['dn']
      if os.path.isdir(d):
        cmd('cd "%s" && git pull %s' % (d, r['href']))
      else:
        cmd('git clone --bare %s "%s"' % (r['href'], d))
      if sync:
        cmd('cd "%s" && git push %s' % (d, r['href']))


@cli.command()
@click.argument('user')
@click.option('--category', default='')
@click.option('--scm', default='')
@click.option('--hook', multiple=True)
@click.option('-h', is_flag=True)
def sync(user, category, scm, hook, h):
  """ Sync all repos to Bitbucket.

  Walks the current directory. Handles only directories which are
  repositories. Creates the repository in Bitbucket if it does not exist yet.
  Does push and then pull.

  You need to provide your Bitbucket username as parameter. The name of
  local directory is used as the name of the Bitbucket repository. You
  can also provide the category in Bitbucket.

  For example: Local dir is "foo". Your username in Bitbucket is "asdf".
  You want to use category "bar". The command is then:

    bbsync sync --category bar asdf

  And the resulting name of the repo in Bitbucket is "bar/foo":

    ssh://hg@bitbucket.org/asdf/bar-foo

  Does not traverse the local directory tree, only one level.

  You can add POST hook URLs with --hook to the synced repos. Allows multiple hooks.
  If -h is provided hooks defined in settings are set to the synced repos.
  """
  for directory in os.listdir('.'):
    if len(category) > 0:
      repo = '/'.join([category, directory])
    else:
      repo = directory
    if os.path.isdir(os.path.join(directory, '.hg')) and scm in ('', 'hg'):
      sync_repo('hg', directory, user, repo, hook, h)
    if os.path.isdir(os.path.join(directory, '.git')) and scm in ('', 'git'):
      sync_repo('git', directory, user, repo, hook, h)


@cli.command()
@click.argument('user')
def ghsync(user):
  """ Sync all repos to Github.

  Walks the current directory. Handles only directories which are
  repositories.

  Assumes remote is "origin". Does push and pull for all heads and tags.

  You need to provide your Github username as parameter. The name of
  local directory is used as the name of the Github repository.
  """
  for directory in os.listdir('.'):
    slug = repo2slug(directory)
    href = 'ssh://git@github.com:%s/%s.git' % (user, slug)
    if os.path.isdir(os.path.join(directory, '.git')):
      cmd('cd "%s" && git push --all -f %s' % (directory, href))
      cmd('cd "%s" && git pull %s' % (directory, href))


@cli.command()
def clear():
  """ Remove working area from all directories.

  Traverse all repositories from current directory and
  remove work areas.
  """

  for directory in os.listdir('.'):
    if os.path.isdir(os.path.join(directory, '.hg')):
      cmd('cd "%s" && hg up -C -r null && hg clean --all' % directory)


@cli.command()
@click.argument('user')
@click.argument('repo')
@click.option('--group', multiple=True)
def groups(user, repo, group):
  """ Grant access for group to repository.
  """

  for g in group:
    group_owner = user
    group_slug, privilege = g.split(':')
    group_access_for_repo(user, repo, group_owner, group_slug, privilege)


@cli.command()
@click.argument('user')
@click.argument('repo')
@click.option('--hook', multiple=True)
@click.option('-h', is_flag=True)
def workarea(user, repo, hook, h):
  """ Sync local workarea to Bitbucket.

  Uses the current directory as source. Does push and then pull.
  Creates the repository in Bitbucket if it does not exist yet.

  You need to provide your Bitbucket username and the name of
  the repo as parameter. If the repo name contains "/" chars they
  are coverted to "-".

  For example: Your username in Bitbucket is "asdf".
  You want to use the repo name "bar/foo". The command is then:

    bbsync workarea asdf bar/foo

  Bitbucket is accessed with:

    ssh://hg@bitbucket.org/asdf/bar-foo

  You can add POST hook URLs with --hook to the synced repos. Allows multiple hooks.
  If -h is provided hooks defined in settings are set to the synced repos.
  """

  directory = '.'
  if os.path.isdir(os.path.join(directory, '.hg')):
    sync_repo('hg', directory, user, repo, hook, h)
  if os.path.isdir(os.path.join(directory, '.git')):
    sync_repo('git', directory, user, repo, hook, h)


@cli.command()
@click.option('--latest', is_flag=True)
@click.option('--publish', is_flag=True)
@click.pass_context
def hg2git(ctx, latest, publish):
  """ Commit identical copy from hg to git.

  BEWARE! Removes all local changes from workarea before doing anything.
  Without confirmation :)

  The tool works by having both .hg and .git workareas in the same
  directory. You can achieve this with few easy steps:

  \b
  1. Clone hg repo
  2. Clone git repo
  3. Copy .git directory from git repo to hg repo root
  4. Delete what is left of git repo workarea

  Git repo is assumed to be in correct state if one is found.
  Creates empty git repo if .git does not exist.

  Tag is created to git repo if hg workarea has a tag.

  The --latest flag causes the hg repo to pull and update
  the workarea to the latest tag in the repo before doing
  anything else.

  The --publish flag also pushes all heads and tags on the git repo
  to the default remote.
  """
  directory = '.'
  init = False
  if os.path.isdir(os.path.join(directory, '.hg')):
    if not os.path.isdir(os.path.join(directory, '.git')):
      cmd('git init .')
      init = True
    if latest:
      cmd('hg pull')
      cmd('hg up -C -r "last(tag())"')
    cmd('hg revert --all && hg clean --all -X .git')
    cmd('git add --all .')
    if ctx.obj['VERBOSE']:
      cmd('git diff --cached && git status')
    cmd('git commit -a -m "`hg id -i`"')
    tag = cmdo('hg id -t').strip()
    if len(tag) > 2 and tag[0] == 'v':
      cmd('git tag "%s"' % tag)
    if publish and not init:
      cmd('git push --all -f')
      cmd('git push --tags -f')


if __name__ == '__main__':
  cli()

