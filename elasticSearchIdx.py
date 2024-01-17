'''

# CURRENTLY:
https://dylancastillo.co/elasticsearch-python/
https://github.com/dylanjcastillo/random/blob/main/elasticsearch.ipynb?ref=dylancastillo.co

# SETTING UP ELASTIC SEARCH
# =========================

# Important: you need elastic search app running separately; the pip thing just connects Python to elastic search

# Step 1: Download and install archive for MacOS (https://www.elastic.co/guide/en/elasticsearch/reference/8.9/targz.html#install-macos)
curl -O https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.9.0-darwin-x86_64.tar.gz
curl https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.9.0-darwin-x86_64.tar.gz.sha512 | shasum -a 512 -c - 
tar -xzf elasticsearch-8.9.0-darwin-x86_64.tar.gz
cd ~/elasticsearch-8.9.0/

# Step 2: Run Elasticsearch from the command line (https://www.elastic.co/guide/en/elasticsearch/reference/8.9/targz.html#targz-running)
./bin/elasticsearch
✅ Elasticsearch security features have been automatically configured!
✅ Authentication is enabled and cluster connections are encrypted.

ℹ️  Password for the elastic user (reset with `bin/elasticsearch-reset-password -u elastic`):
  m0zpo+0Iv1Bd0Q54XM_I

ℹ️  HTTP CA certificate SHA-256 fingerprint:
  7da59cfc704f2d5a4eed1fc57980d1b52f6bd3a572e0fc4d5c2f1fa52fc1b1a3

ℹ️  Configure Kibana to use this cluster:
• Run Kibana and click the configuration link in the terminal when Kibana starts.
• Copy the following enrollment token and paste it into Kibana in your browser (valid for the next 30 minutes):
  eyJ2ZXIiOiI4LjkuMCIsImFkciI6WyIxMC4wLjAuNjI6OTIwMCJdLCJmZ3IiOiI3ZGE1OWNmYzcwNGYyZDVhNGVlZDFmYzU3OTgwZDFiNTJmNmJkM2E1NzJlMGZjNGQ1YzJmMWZhNTJmYzFiMWEzIiwia2V5IjoiTmdJV25va0JvYWt5S09zQXlCYWI6cGppSUVHb1dTWW00YUVHdzJ3M0NLQSJ9

ℹ️  Configure other nodes to join this cluster:
• On this node:
  ⁃ Create an enrollment token with `bin/elasticsearch-create-enrollment-token -s node`.
  ⁃ Uncomment the transport.host setting at the end of config/elasticsearch.yml.
  ⁃ Restart Elasticsearch.
• On other nodes:
  ⁃ Start Elasticsearch with `bin/elasticsearch --enrollment-token <token>`, using the enrollment token that you generated.

# Step 3: Verifying HTTPS with CA certificates (https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/connecting.html#_verifying_https_with_ca_certificates)
'''

# BASIC MODULES
import numpy as np
import pandas as pd
import os
import time
import zlib
import pickle
import base64 
import json
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, parallel_bulk
from dotenv import load_dotenv,find_dotenv


load_dotenv(find_dotenv())


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

def compress_and_base64_encode(data):
    # Convert the dictionary to a string representation (JSON format in this case)

    json_data = json.dumps(data,cls=NpEncoder)
    
    # Compress the string using zlib
    compressed_data = zlib.compress(json_data.encode('utf-8'))
    
    # Base64 encode the compressed data
    encoded_data = base64.b64encode(compressed_data).decode('utf-8')
    
    return encoded_data

def base64_decode_and_decompress(encoded_data):
    # Base64 decode the data
    compressed_data = base64.b64decode(encoded_data)
    
    # Decompress the data using zlib
    decompressed_data = zlib.decompress(compressed_data)
    
    # Convert the decompressed string back to a dictionary
    decoded_data = json.loads(decompressed_data.decode('utf-8'))
    
    return decoded_data

def get_all_values_by_key(data, target_key):
    result = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key:
                result.append(value)
            elif isinstance(value, (dict, list)):
                result.extend(get_all_values_by_key(value, target_key))
    elif isinstance(data, list):
        for item in data:
            result.extend(get_all_values_by_key(item, target_key))

    return result


def index_es_data(df,index_name):
    mappings = {}
    mappings['properties'] = {}
    mappings['properties']['authfull'] = {'type':'text'}
    mappings['properties']['cntry'] = {'type':'text'}
    mappings['properties']['inst_name'] = {'type':'text'}
    mappings['properties']['sm-field'] = {'type':'text'}
    mappings['properties']['data'] = {'type':'binary'}

    client.indices.create(index=index_name, mappings = mappings)

    def doc_generator(df):
        df_iter = enumerate(df)
        for index, document in df_iter:
            yield {
                    "_index": index_name,
                    "_type": "_doc",
                    "_id" : index,
                    "_source": {"authfull":document,
                                "cntry": list(set(get_all_values_by_key(df[document], "cntry")))[-1],
                                "inst_name": list(set(get_all_values_by_key(df[document], "inst_name")))[-1],
                                "sm-field": list(set(get_all_values_by_key(df[document], "sm-field")))[-1],
                                "data":compress_and_base64_encode(df[document])}
                }
            

    for success, info in parallel_bulk(client, doc_generator(df), raise_on_error=False):
        if not success:
            print('A document failed:', info)

    client.indices.refresh(index=index_name)
    print(f"Done {index_name}")

def index_es_data_agg(df,key_name,index_name):
    mappings = {}
    mappings['properties'] = {}
    mappings['properties'][key_name] = {'type':'text'}
    mappings['properties']['data'] = {'type':'binary'}

    client.indices.create(index=index_name, mappings = mappings)

    def doc_generator(df):
        df_iter = enumerate(df)
        for index, document in df_iter:
            yield {
                    "_index": index_name,
                    "_type": "_doc",
                    "_id" : index,
                    "_source": {key_name:document,
                                "data":compress_and_base64_encode(df[document])}
                }
            

    for success, info in parallel_bulk(client, doc_generator(df), raise_on_error=False):
        if not success:
            print('A document failed:', info)

    client.indices.refresh(index=index_name)
    print(f"Done {index_name}")

# ================== Password for the 'elastic' user generated by Elasticsearch
ELASTIC_PASSWORD = "ELASTIC_PW"

# ================== Create the client instance
es = Elasticsearch([os.environ.get("ES_URL")])

# client = Elasticsearch(
#     "https://localhost:9200",
#     ca_certs="/PATH/TO/elasticsearch-8.9.0/config/certs/http_ca.crt",
#     basic_auth=("elastic", ELASTIC_PASSWORD)
# )
# print(client.ping()) # should output True!

# To remove stuff before indexing
# client.options(ignore_status=[400,404]).indices.delete(index='citations')
# client.options(ignore_status=[400,404]).indices.delete(index='citationsobj3')
# client.options(ignore_status=[400,404]).indices.delete(index='citationsobj2')


# df = pickle.load(open("composite_career.p", "rb"))
# index_es_data(df,"career")

# df = pickle.load(open("composite_singleyr.p", "rb"))
# index_es_data(df,"singleyr")

# client.options(ignore_status=[400,404]).indices.delete(index='career_cntry')
# df = pickle.load(open("career_aggregate_cntry.p", "rb"))
# index_es_data_agg(df,'cntry',"career_cntry")

# client.options(ignore_status=[400,404]).indices.delete(index='career_field')
# df = pickle.load(open("career_aggregate_field.p", "rb"))
# index_es_data_agg(df,'sm-field',"career_field")

# client.options(ignore_status=[400,404]).indices.delete(index='career_inst')
# df = pickle.load(open("career_aggregate_inst.p", "rb"))
# index_es_data_agg(df,'inst_name',"career_inst")

# client.options(ignore_status=[400,404]).indices.delete(index='singleyr_inst')
# df = pickle.load(open("singleyr_aggregate_inst.p", "rb"))
# index_es_data_agg(df,'inst_name',"singleyr_inst")

# client.options(ignore_status=[400,404]).indices.delete(index='singleyr_cntry')
# df = pickle.load(open("singleyr_aggregate_cntry.p", "rb"))
# index_es_data_agg(df,'cntry',"singleyr_cntry")

# client.options(ignore_status=[400,404]).indices.delete(index='singleyr_field')
# df = pickle.load(open("singleyr_aggregate_field.p", "rb"))
# index_es_data_agg(df,'sm-field',"singleyr_field")