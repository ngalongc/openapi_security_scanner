import schemathesis
import json
import os
import requests
import itertools

def format_md_result(path,status_code,resp_len,scope,username,method):
  return path + divider + status_code + divider + resp_len + divider + scope + divider + username + divider + method + divider+"\n"


def expand_paths_to_list(path_examples):
	keys = path_examples.keys()
	values = (path_examples[key] for key in keys)
	combinations = [dict(zip(keys, combination)) for combination in itertools.product(*values)]
	return combinations


def main(path_examples):
  result_md = ""
  for targeted_endpoint in targeted_endpoints:
    for credential in credentials: # credentials = 
      for cred_set in credentials[credential]:
        access_token = cred_set['access_token']
        case = schema[targeted_endpoint]["GET"].make_case(path_parameters=path_examples,query=targeted_endpoints[targeted_endpoint])
        response = case.call(headers={"Authorization":"Bearer " + access_token})
        single_result = format_md_result(
          status_code=str(response.status_code),
          path=case.formatted_path,
          resp_len=str(len(response.text)),
          scope=cred_set['scope'],
          username=credential, # snapmortgage
          method="GET"
          )
        result_md += single_result
        #targeted_endpoint = {"/orgs/{org}/repos":{"type":"all"}}
  return result_md


## Initiate the variables
base_url = os.getenv('OPENAPI_BASE_URL')
targeted_endpoints = json.loads(os.getenv('OPENAPI_ENDPOINTS'))
path_examples = json.loads(os.getenv('OPENAPI_PATHS'))
credentials = json.loads(os.getenv('OPENAPI_CREDS'))

schema = schemathesis.from_path("api.yaml",base_url=base_url)

divider = "|"
md_header = "| - | Status | Length | Scope | Username | Method |\n"  +  "| - | - | - | - | - | -|\n"


## Make path_examples to become a list with all possible combinations
path_examples = expand_paths_to_list(path_examples)


for path_param in path_examples:
  md_header += main(path_param)

result_response = requests.post(json={"text":md_header},url="https://gitlab.com/api/v4/markdown")
result_json = json.loads(result_response.text)
html = result_json['html']

with open('sample.html',mode='w') as f:
	f.write(html)

