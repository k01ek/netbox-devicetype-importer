import requests

from jinja2 import Template


class GQLError(Exception):
    default_message = None

    def __init__(self, message=None):
        if message is None:
            self.message = self.default_message
        else:
            self.message = message
        super().__init__(message)


class GitHubAPI():
    def __init__(self, url=None, token=None, owner=None, repo=None):
        self.session = requests.session()
        self.session.headers.update({'Accept': 'application/vnd.github.v3+json'})
        if token:
            self.session.headers.update({'Authorization': f'token {token}'})
        self.dt_dir = 'device-types'
        self.url = f'https://api.github.com/repos/{owner}/{repo}/contents/'

    def get_vendors(self):
        result = {}
        url = f'{self.url}{self.dt_dir}'
        response = self.session.get(url)
        if response.ok:
            for vendor in response.json():
                result[vendor['name']] = vendor['path']
        return result

    def get_models(self, vendor):
        result = {}
        url = f'{self.url}{self.dt_dir}/{vendor}'
        response = self.session.get(url)
        if response.ok:
            for model in response.json():
                result[model['name']] = {
                    'path': model['path'],
                    'sha': model['sha'],
                    'download_url': model['download_url']
                }
        return result

    def get_tree(self):
        '''
        {'cisco': {
            '2950.yaml': {'path': '', 'sha': '', 'download_url': ''}
            }
        }
        '''
        result = {}
        vendors = self.get_vendors()
        for vendor in vendors:
            models = self.get_models(vendor)
            result[vendor] = models
        return result

    def get_files(self, data):
        return {}


class GitHubGQLAPI():
    tree_query = """
{
  repository(owner: "{{ owner }}", name: "{{ repo }}") {
    object(expression: "master:{{ path }}") {
      ... on Tree {
        entries {
          name
          type
          object {
            ... on Blob {
              oid
            }
            ... on Tree {
              entries {
                name
                type
                object {
                  ... on Blob {
                    oid
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""
    files_query = """
{
    repository(owner: "{{ owner }}", name: "{{ repo }}") {
        {% for sha, path in data.items() %}
        sha_{{ sha }}: object(expression: "master:{{ root_path }}/{{ path }}") {
            ... on Blob {
                text
            }
        }
        {% endfor %}
    }
}
"""

    def __init__(self, url='https://api.github.com/graphql', token=None, owner=None, repo=None):
        self.session = requests.session()
        self.session.headers.update({'Authorization': f'token {token}'})
        self.path = 'device-types'
        self.url = url
        self.token = token
        self.owner = owner
        self.repo = repo

    def get_query(self, query):
        result = {}
        response = self.session.post(url=self.url, json={'query': query})
        if response.ok:
            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError:
                raise GQLError('Cant parse message from GitHub. {}'.format(response.text))
            err = result.get('errors')
            if err:
                # fix that
                raise GQLError(message=err[0].get('message'))
            return result
        else:
            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError:
                raise GQLError('Cant parse message from GitHub. {}'.format(response.text))
            err = result.get('errors')
            if err:
                raise GQLError(message=err[0].get('message'))
            raise GQLError(result.get('message'))
        return result

    def get_tree(self):
        result = {}
        template = Template(self.tree_query)
        query = template.render(owner=self.owner, repo=self.repo, path=self.path)
        data = self.get_query(query)
        if not data:
            return result
        for vendor in data['data']['repository']['object']['entries']:
            result[vendor['name']] = {}
            for model in vendor['object']['entries']:
                result[vendor['name']].update({model['name']: {'sha': model['object']['oid']}})
        return result

    def get_files(self, query_data):
        '''
        data = {'sha': 'venodor/model'}
        result = {'sha': 'yaml_text'}
        '''
        result = {}
        if not query_data:
            return result
        template = Template(self.files_query)
        query = template.render(owner=self.owner, repo=self.repo, data=query_data, root_path=self.path)
        data = self.get_query(query)
        for k, v in data['data']['repository'].items():
            result[k.replace('sha_', '')] = v['text']
        return result
