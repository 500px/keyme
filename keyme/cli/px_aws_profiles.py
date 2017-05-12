#!/usr/bin/env python

from __future__ import print_function
import click
import json
import os
import re
import py
import sys
import yaml
from keyme import KeyMe


class Config(dict):

    def __init__(self, *args, **kwargs):
        self.config = py.path.local(os.path.expanduser('~/.aws/keyme.yaml'))  # A
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


def generate_keys(event, context={}):
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

def get_env_names(config, context={}):
    return config['accounts'].keys()

def get_env(config, env, context={}):
    return config['accounts'][env]

def get_google_account(config, context={}):
    return config['google']

def read_path(path, context={}):
    file_handle = open_path(path)
    file_contents = file_handle.read()
    file_handle.close()
    return file_contents

def open_path(path, mode='r', context={}):
    return py.path.local(os.path.expanduser(path)).open(mode)

def read_aws_config(aws_config_path, context={}):
    return read_path(aws_config_path)

def read_aws_credentials(aws_credentials_path, context={}):
    return read_path(aws_credentials_path)

def get_profiles_from_config_file(aws_file_path, context={}):
    regex = re.compile(r'^\[(profile )?(?P<name>[^\n\r]+(?=[\s\]]{0,1}))][\n\r](?P<keys>(?:[^\[$]+)+)', re.MULTILINE)
    aws_config_content = read_aws_config(aws_file_path)
    profiles = {}
    for m in regex.finditer(aws_config_content):
        match_dict = m.groupdict()
        profiles[match_dict['name']] = {}
        for keyval in match_dict['keys'].strip().split('\n'):
            key, value = re.split("\s*=\s*(?=[^$])", keyval)
            profiles[match_dict['name']][key.strip()] = value.strip()
    return profiles

def get_profiles(aws_config_path="~/.aws/config", aws_credentials_path="~/.aws/credentials", context={}):
    aws_config_profiles = get_profiles_from_config_file(aws_config_path)
    aws_credentials_profiles = get_profiles_from_config_file(aws_credentials_path)
    for profile_name, profile_vars in aws_credentials_profiles.iteritems():
        if profile_name in aws_config_profiles.keys():
            aws_config_profiles[profile_name].update(profile_vars)
        else:
            aws_config_profiles[profile_name] = profile_vars
    return aws_config_profiles

def write_aws_configuration_profile_stanza(file_handle, profile_name, profile_keys, use_profile_keyword=True, context={}):
    if not profile_keys:
        return
    if use_profile_keyword and profile_name != "default":
        print("[profile " + profile_name + "]", file=file_handle)
    else:
        print("[" + profile_name + "]", file=file_handle)
    for k, v in profile_keys.iteritems():
        print(k + " = " + v, file=file_handle)
    print("", file=file_handle)

def add_defaults_to_profile(profile, *args, **kwargs):
    for kw, kwv in kwargs.iteritems():
        if kw not in profile:
            profile[kw] = kwv
    return profile

def write_aws_configuration_file(profiles, aws_config_path="~/.aws/config", config_vars_to_use=["region", "output", "aws_access_key_id", "aws_secret_access_key", "aws_session_token"], use_profile_keyword=True, default_region="us-east-1", default_output_type="text", context={}):

    if not profiles:
        return

    if 'default' in profiles.keys():
       default = profiles['default']
       del profiles['default']
    else:
        default = {}

    add_defaults_to_profile(default, region=default_region, output=default_output_type)
    default = {var: value  for var, value in default.iteritems() if var in config_vars_to_use }
    aws_file_handle = open_path(aws_config_path, 'w')
    write_aws_configuration_profile_stanza(aws_file_handle, "default", default)

    for profile_name in sorted(profiles.keys()):
        profile_config = profiles[profile_name]
        add_defaults_to_profile(profile_config, region=default_region, output=default_output_type)
        profile_vars = {var: value  for var, value in profile_config.iteritems() if var in config_vars_to_use }
        write_aws_configuration_profile_stanza(aws_file_handle, profile_name, profile_vars, use_profile_keyword)
    aws_file_handle.close()

def put_profiles(profiles, aws_config_path="~/.aws/config", aws_credentials_path="~/.aws/credentials", default_region="us-east-1", default_output_type="text", context={}):
    write_aws_configuration_file(profiles, aws_config_path, ["region", "output"], True, default_region, default_output_type)
    write_aws_configuration_file(profiles, aws_credentials_path, ["aws_access_key_id", "aws_secret_access_key", "aws_session_token"], False, default_region, default_output_type)

def get_env_config_for_profile(config, profile, context={}):
    for account_name, account_config in config['accounts'].iteritems():
        if account_config['profile'] == profile:
            return account_name

def get_keys(config, account_name, password, mfa, context={}):
    google_account = get_google_account(config)
    aws_config = get_env(config, account_name)
    k = generate_keys(
        {'username': google_account['username'],
         'password': password,
         'mfa_code': mfa,
         'role': aws_config['role'],
         'principal': aws_config['principal'],
         'idpid': google_account['idp'],
         'spid': aws_config['sp'],
         'region': aws_config['region'],
         'duration': aws_config['duration_seconds']
         },
        {}
    )
    return k

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
        print(get_env(config, env))

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

@cli.command('test')
@pass_config
def test(config):
    put_profiles(get_profiles())

@cli.command('profile')
@pass_config
@click.option('--awsaccount', '-e', help="AWS account name (from keyme config stanza)", required=True)
@click.option('--password', '-p', help="Enter your Google password to override config file.")
@click.option('--mfa', '-m', help="Use MFA to login to Google.")
@click.option('--exports', '-s', is_flag=True, help='Print export lines for AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_SESSION_TOKEN, AWS_DEFAULT_REGION.', default=False)
@click.option('--default', '-d', is_flag=True, help="Output AWS_DEFAULT_PROFILE export line.", default=False)
def profile(config, awsaccount, password, mfa, exports, default):
    google_account = get_google_account(config)
    if password is None and 'password' not in google_account:
        click.echo("Password is required!")
    elif 'password' in google_account:
        password = google_account['password']

    keys = get_keys(config, awsaccount, password, mfa)

    profile = config['accounts'][awsaccount]['profile']
    profiles = get_profiles()
    if profile not in profiles:
        profiles[profile] = {}
    profiles[profile]['aws_access_key_id']          = keys['aws']['access_key']
    profiles[profile]['aws_secret_access_key']      = keys['aws']['secret_key']
    profiles[profile]['aws_session_token']          = keys['aws']['session_token']
    profiles[profile]['region']                     = config['accounts'][awsaccount]['region']

    put_profiles(profiles)

    if exports:
        click.echo('export AWS_ACCESS_KEY_ID="' + keys['aws']['access_key'] + '"')
        click.echo('export AWS_SECRET_ACCESS_KEY="' + keys['aws']['secret_key'] + '"')
        click.echo('export AWS_SESSION_TOKEN="' + keys['aws']['session_token'] + '"')
        click.echo('export AWS_DEFAULT_REGION="' + config['accounts'][awsaccount]['region'] + '"')

    if default:
        click.echo('export AWS_DEFAULT_PROFILE="' + profile + '"')

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
        env_info = get_env(config, env)
        aws_role = env_info['role']
        aws_principal = env_info['principal']
        aws_region = env_info['region']
        duration_seconds = env_info['duration_seconds']
        aws_sp = env_info['sp']
        google_account_info = get_google_account(config)
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
