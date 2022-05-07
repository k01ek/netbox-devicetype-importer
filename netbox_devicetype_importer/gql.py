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


class GitHubGqlAPI:
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

    def __init__(self, url='https://api.github.com/graphql', token=None, owner=None, repo=None, path=None):
        self.session = requests.session()
        self.session.headers.update({'Authorization': f'token {token}'})
        self.path = path
        self.url = url
        self.token = token
        self.owner = owner
        self.repo = repo

    def get_query(self, query):
        response = self.session.post(url=self.url, json={'query': query})
        try:
            result = response.json()
        except requests.exceptions.JSONDecodeError:
            raise GQLError('Cant parse message from GitHub. {}'.format(response.text))
        err = result.get('errors')
        if err:
            # fix that
            raise GQLError(message=err[0].get('message'))
        if response.ok:
            return result
        else:
            raise GQLError(result.get('message'))

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
        """
        data = {'sha': 'vendor/model'}
        result = {'sha': 'yaml_text'}
        """
        result = {}
        if not query_data:
            return result
        template = Template(self.files_query)
        query = template.render(owner=self.owner, repo=self.repo, data=query_data, root_path=self.path)
        data = self.get_query(query)
        for k, v in data['data']['repository'].items():
            result[k.replace('sha_', '')] = v['text']
        return result
