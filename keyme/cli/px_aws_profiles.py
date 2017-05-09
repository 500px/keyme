#!/usr/bin/env python

import click
import json
import os
import py
import sys
import yaml
from keyme import KeyMe


class Config(dict):

    def __init__(self, *args, **kwargs):
        self.config = py.path.local().join('keyme.yaml')  # A
        print self.config

        super(Config, self).__init__(*args, **kwargs)

    def load(self):
        """load a yaml config file from disk"""
        try:
            self.update(yaml.load(self.config.read()))  # B
        except py.error.ENOENT:
            pass

    def save(self):
        self.config.ensure()
        with self.config.open('w') as f:  # B
            f.write(yaml.dump(self))


def generate_keys(event, context):
    username = event.get('username')
    password = event.get('password')
    mfa_code = event.get('mfa_code')
    region = event.get('region', 'us-east-1')

    # The following, we expect, to come from $stageVariables
    idp = event.get('idpid')
    sp = event.get('spid')
    role = event.get('role')
    principal = event.get('principal')

    # Duplication is to avoid defaulting values in the class
    # - thats logic we shouldn't be doing there
    return KeyMe(username=username,
                 password=password,
                 mfa_code=mfa_code,
                 idp=idp,
                 sp=sp,
                 region=region,
                 role=role,
                 principal=principal).key()

def get_env_names(config, context):
    return config['accounts'].keys()

def get_env(config, env, context):
    return config['accounts'][env]

def get_google_account(config, context):
    return config['google']

pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group(chain=True)
@pass_config
def cli(config):
    config.load()
    pass


@cli.command('show-config')
@pass_config
def show_config(config):
    data = yaml.dump(config)
    click.echo(data)

@cli.command('show-env-config')
@pass_config
@click.option('--env', '-e', help="Environment name given during setup")
def show_env_config(config, env):
    if env is not None:
        print get_env(config, env, {})

@cli.command('init')
@pass_config
@click.option('--update', help="update configuration for given env name")
def setup(config, update):
    if update not in config:
        name = click.prompt(
            'Please enter a name for this config', default='default')
    else:
        name = update

    idp_id = click.prompt('Please enter your google idp id')
    sp_id = click.prompt('Please enter your aws sp id')
    aws_region = click.prompt(
        'Which AWS Region do you want to be default?', default='us-east-1')
    principal_arn = click.prompt('Please provide your default principal ARN')
    role_arn = click.prompt('Please provide your default role arn')
    duration_seconds = click.prompt(
        'Please provide the duration in seconds of the sts token', default=3600, type=int)
    data = {
        'idpid': idp_id,
        'spid': sp_id,
        'region': aws_region,
        'principal': principal_arn,
        'role': role_arn,
        'duration_seconds': duration_seconds
    }
    if click.confirm('Do you want to provide a default username?'):
        username = click.prompt('Please enter your default username')
        data['username'] = username
    if click.confirm('Do your want to enable MFA tokens?'):
        mfa_token = True
    else:
        mfa_token = None

    data['mfa'] = mfa_token
    config[name] = data
    config.save()


@cli.command('get')
@pass_config
@click.option('--mfa', '-m', is_flag=True, help="Enables MFA if disabled in default configuration")
@click.option('--username', '-u', help="Allows overriding of the stored username")
@click.option('--password', '-p', prompt=True, hide_input=True, confirmation_prompt=False)
@click.option('--idp', '-i', help="Allows overrideing of the IDP id", default='C02mxo447')
@click.option('--sp', '-s', help="Allows overriding of the store SP id ", default='293517734924')
@click.option('--principal', '-a', help='Allows overriding of the store principal', default='arn:aws:iam::297478900136:saml-provider/500pxGoogleApps')
@click.option('--role', '-r', help='Allows overriding of the stored role ARN', default='arn:aws:iam::297478900136:role/500pxGAppsPlatform')
@click.option('--region', help='Allows changing the aws region by overriding default stored value', default='us-east-1')
@click.option('--env', '-e', help="Environment name given during setup")
@click.option('--duration', '-d', help="override stored duration for creds from sts", default='3600')
def get(config, mfa, username, password, idp, sp, principal, role, region, env, duration):
    if env is not None:
        env_info = get_env(config, env, {})
        aws_role = env_info['role']
        aws_principal = env_info['principal']
        aws_region = env_info['region']
        duration_seconds = env_info['duration_seconds']
        aws_sp = env_info['sp']
        google_account_info = get_google_account(config, {})
        google_username = google_account_info['username']
        google_idp = google_account_info['idp']
    else:
        aws_role = role
        aws_principal = principal
        google_idp = idp
        aws_sp = sp
        aws_region = region
        duration_seconds = duration

    if username is not None:
        google_username = username

    if mfa or (env is not None and mfa in google_account_info):
        mfa = click.prompt('Please enter MFA Token')
    else:
        mfa = None

    print "Username: " + google_username
    # print "MFA Code: " + mfa
    print "AWS Role" + aws_role
    print "AWS Principal Identity Provider: " + aws_principal
    print "Google idp: " + google_idp
    print "AWS SP: " + aws_sp
    print "AWS Region: " + aws_region
    print "Login Duration: " + str(duration_seconds)

    k = generate_keys(
        {'username': google_username,
         'password': password,
         'mfa_code': mfa,
         'role': aws_role,
         'principal': aws_principal,
         'idpid': google_idp,
         'spid': aws_sp,
         'region': aws_region,
         'duration': duration_seconds
         },
        {}
    )

    click.echo('export AWS_ACCESS_KEY=\'' +
               k['aws']['access_key'].encode('utf-8') + '\'')
    click.echo('export AWS_SECRET_ACCESS_KEY=\'' +
               k['aws']['secret_key'].encode('utf-8') + '\'')
    click.echo('export AWS_SESSION_TOKEN=\'' +
               k['aws']['session_token'].encode('utf-8') + '\'')
