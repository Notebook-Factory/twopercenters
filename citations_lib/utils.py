import numpy as np
import pandas as pd

import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import plot
import plotly.express as px
import plotly.colors
from plotly.subplots import make_subplots
import country_converter as coco
import os
import json 
import pickle
import base64
import zlib
import math 

from elasticsearch import Elasticsearch, helpers, exceptions
from dotenv import load_dotenv,find_dotenv


load_dotenv(find_dotenv())
#es = Elasticsearch([os.environ.get("ES_URL")])
es = Elasticsearch(["http://dokku-elasticsearch-citedb:9200"])

def write_pickle(file,filename):
    with open(filename, 'wb') as handle:
        pickle.dump(file, handle, protocol=pickle.HIGHEST_PROTOCOL)

def write_json(in_file,filename):
    with open(filename, "w") as file:
        json.dump(in_file, file)

def read_json(filename):
    with open(filename, "r") as file:
        data = json.load(file)
        return data


def es_scroll(index, query_body, page_size=100, debug=False, scroll='2m'):
    page = es.search(index=index, scroll=scroll, size=page_size, body=query_body)
    sid = page['_scroll_id']
    scroll_size = page['hits']['total']['value']
    total_pages = math.ceil(scroll_size/page_size)
    page_counter = 0
    if debug: 
        print('Total items : {}'.format(scroll_size))
        print('Total pages : {}'.format( math.ceil(scroll_size/page_size) ) )
    # Start scrolling
    while (scroll_size > 0):
        # Get the number of results that we returned in the last scroll
        scroll_size = len(page['hits']['hits'])
        if scroll_size>0:
            if debug: 
                print('> Scrolling page {} : {} items'.format(page_counter, scroll_size))
            yield total_pages, page_counter, scroll_size, page
        # get next page
        page = es.scroll(scroll_id = sid, scroll = '2m')
        page_counter += 1
        # Update the scroll ID
        sid = page['_scroll_id']

def get_index_cat(index_name):
    params = {"bytes":"b","format":"json"}
    return es.cat.indices(index=index_name,params=params)

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

def es_result_pick(result,field, nohit = ['']):
    if result is not None:
        if field == 'data':
            return base64_decode_and_decompress(result[f'_source.{field}'])
        elif (f'_source.{field}' in result.keys()):
            return list(result[f'_source.{field}'])
        else:
            res = nohit
    else:
        res = nohit
    return res

def get_auth_years(data):
    #data = es_result_pick(result,'data', None)
    if data:
        years = []
        for dat in data.keys():
            if dat.split('_')[-1] != 'log':
                years.append(dat.split('_')[-1])
        return years
    else:
        return None

def get_es_aggregate(group,group_name,prefix):
    data  = {}
    if group == 'cntry':
        cur_country = coco.convert(names = group_name, to = 'ISO3')
        results = get_es_results(cur_country.lower(),f'{prefix}_{group}','cntry',True)
        data = es_result_pick(results, 'data', None)
    elif group == "sm-field":
        results = get_es_results(group_name,f'{prefix}_field','sm-field')
        data = es_result_pick(results, 'data', None)
    elif group == "inst_name":
        results = get_es_results(group_name,f'{prefix}_inst','inst_name')
        data = es_result_pick(results, 'data', None)
    return data

def get_es_results(search_term,idx_name, search_fields, exact = False):
    if search_term:
        if not exact:
            result = es.search(
                index=idx_name,
                size=100, 
                body={
                    "query": {
                        "multi_match" : {
                            "query": search_term, 
                            #"type": "phrase_prefix",
                            "operator": "and",
                            "fuzziness": "auto",
                            "fields": search_fields
                        },
                    }
                })
        else:
            result = es.search(
                index=idx_name,
                size=100,
                body={
                    "query": {
                        "term" : {
                            search_fields: search_term
                        },
                    }
                })
        if 'hits' in result and 'hits' in result['hits'] and result['hits']['hits']:
                return pd.json_normalize(result['hits']['hits'])
        else:
            return None

def base64_decode_and_decompress(encoded_data,flg=True):

    # HARDCODED 
    # pandas series to string
    if flg:
        encoded_data = encoded_data[0]

    # Base64 decode the data
    compressed_data = base64.b64decode(encoded_data)
    
    # Decompress the data using zlib
    decompressed_data = zlib.decompress(compressed_data)
    
    # Convert the decompressed string back to a dictionary
    decoded_data = json.loads(decompressed_data.decode('utf-8'))
    
    return decoded_data
def get_metric_long_name(career, yr, metric, include_year = True):
    yrs = [2017, 2018, 2019, 2020, 2021]
    if yr == 0: year = 2017
    if yr != 0 and career == False: yr = yr + 1
    year = yrs[yr]
    if include_year == True: metric_name_dict = {
        'authfull':'author name',
        'inst_name':'institution name (large institutions only)',
        'cntry':'country associated with most recent institution',
        'np':f'number of papers from 1960 to {year}',
        'firstyr':'year of first publication',
        'lastyr':'year of most recent publication',
        'rank (ns)':'rank based on composite score c', 
        'nc (ns)':f'total cites from 1996 to {year}', 
        'h (ns)':f'h-index as of the end of {year}', 
        'hm (ns)':f'hm-index as of end-{year}',
        'nps (ns)':'number of single authored papers',
        'ncs (ns)':'total cites to single authored papers', 
        'cpsf (ns)':'number of single + first authored papers', 
        'ncsf (ns)':'total cites to single + first authored papers', 
        'npsfl (ns)':'number of single + first + last authored papers', 
        'ncsfl (ns)':'total cites to single + first + last authored papers',
        'c (ns)':'composite score', 
        'npciting (ns)':'number of distinct citing papers', 
        'cprat (ns)':'ratio of total citations to distinct citing papers', 
        'np cited (ns)':f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
        'self%':'self-citation percentage', 
        'rank':'rank based on composite score c', 
        'nc':f'total cites 1996-{year}', 
        'h':f'h-index as of end-{year}',
        'hm':f'hm-index as of end-{year}', 
        'nps':'number of single authored papers',
        'ncs':'total cites to single authored papers', 
        'cpsf':'number of single + first authored papers', 
        'ncsf':'total cites to single + first authored papers', 
        'npsfl':'number of single + first + last authored papers', 
        'ncsfl':'total cites to single + first + last authored papers',
        'c':'composite score', 
        'npciting':'number of distinct citing papers', 
        'cprat':'ratio of total citations to distinct citing papers', 
        'np cited':f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
        'np_d':f'# papers 1960-{year} in titles that are discontinued in Scopus', 
        'nc_d':f'total cites 1996-{year} from titles that are discontinued in Scopus', 
        'sm-subfield-1':'top ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-1-frac':'associated category fraction',
        'sm-subfield-2':'second ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-2-frac':'associated category fraction', 
        'sm-field':'top ranked higher-level Science-Metrix category (field) for author', 
        'sm-field-frac':'associated category fraction',
        'rank sm-subfield-1':'rank of c within category sm-subfield-1', 
        'rank sm-subfield-1 (ns)':'rank of c (ns) within category sm-subfield-1', 
        'sm-subfield-1 count':'total number of authors within category sm-subfield-1'}
    else: metric_name_dict = {
        'authfull':'author name',
        'inst_name':'institution name (large institutions only)',
        'cntry':'country associated with most recent institution',
        'np':f'number of papers',
        'firstyr':'year of first publication',
        'lastyr':'year of most recent publication',
        'rank (ns)':'rank based on composite score c', 
        'nc (ns)':f'total cites', 
        'h (ns)':f'h-index', 
        'hm (ns)':f'hm-index',
        'nps (ns)':'number of single authored papers',
        'ncs (ns)':'total cites to single authored papers', 
        'cpsf (ns)':'number of single + first authored papers', 
        'ncsf (ns)':'total cites to single + first authored papers', 
        'npsfl (ns)':'number of single + first + last authored papers', 
        'ncsfl (ns)':'total cites to single + first + last authored papers',
        'c (ns)':'composite score', 
        'npciting (ns)':'number of distinct citing papers', 
        'cprat (ns)':'ratio of total citations to distinct citing papers', 
        'np cited (ns)':f'number of papers published since 1960 that have been cited at least', # since 1996 for career wide!
        'self%':'self-citation percentage', 
        'rank':'rank based on composite score c', 
        'nc':f'total cites', 
        'h':f'h-index',
        'hm':f'hm-index', 
        'nps':'number of single authored papers',
        'ncs':'total cites to single authored papers', 
        'cpsf':'number of single + first authored papers', 
        'ncsf':'total cites to single + first authored papers', 
        'npsfl':'number of single + first + last authored papers', 
        'ncsfl':'total cites to single + first + last authored papers',
        'c':'composite score', 
        'npciting':'number of distinct citing papers', 
        'cprat':'ratio of total citations to distinct citing papers', 
        'np cited':f'number of papers published since 1960 that have been cited at least', # since 1996 for career wide!
        'np_d':f'# papers since 1960 in titles that are discontinued in Scopus', 
        'nc_d':f'total cites since 1996 from titles that are discontinued in Scopus', 
        'sm-subfield-1':'top ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-1-frac':'associated category fraction',
        'sm-subfield-2':'second ranked Science-Metrix category (subfield) for author', 
        'sm-subfield-2-frac':'associated category fraction', 
        'sm-field':'top ranked higher-level Science-Metrix category (field) for author', 
        'sm-field-frac':'associated category fraction',
        'rank sm-subfield-1':'rank of c within category sm-subfield-1', 
        'rank sm-subfield-1 (ns)':'rank of c (ns) within category sm-subfield-1', 
        'sm-subfield-1 count':'total number of authors within category sm-subfield-1'}
    return metric_name_dict[metric]

def get_inst_field_cntry(data, prefix, year):
    inst = data[f'{prefix}_{year}']['inst_name']
    field = data[f'{prefix}_{year}']['sm-field']
    cntry = data[f'{prefix}_{year}']['cntry']
    return {'cntry': cntry, 'field': field, 'inst': inst}

def try_catch_return(names,prefix,ent1,ent2):
    results = get_es_results(names,f'{prefix}_{ent1}',ent2)
    data = es_result_pick(results,'data', None)
    if data is None:
        results = get_es_results(names,f'{prefix}_{ent1}',ent2,True)
        data = es_result_pick(results,'data', None)
    return data

def r2dec(value):
    if isinstance(value, str):
        return value  # If it's a string, return it as is
    else:
        try:
            # Try to convert to float and round to 2 decimals
            rounded_value = round(float(value), 2)
            return rounded_value
        except (ValueError, TypeError):
            # If conversion to float fails, or if the value is not numeric, return the original value
            return value

def get_metric_summary(data, prefix, year, metric, stat):
    if stat == 'median':
        idx = 2
    elif stat == 'min':
        idx = 0
    elif stat == 'max':
        idx = 4
    elif stat == 'q1':
        idx = 1
    elif stat == 'q3':
        idx = 3
    names = get_inst_field_cntry(data, prefix, year)
    # Enforce exact match for country

    results_cntry = get_es_results(names['cntry'],f'{prefix}_cntry','cntry',True)
    data_cntry = es_result_pick(results_cntry,'data', None)
    data_field = try_catch_return(names['field'],prefix,'field',"sm-field")
    data_inst = try_catch_return(names['inst'],prefix,'inst',"inst_name")
    own = data[f'{prefix}_{year}'][metric]
    if metric == 'self%':
           own = own*100
    if data_cntry:
       #print(data_cntry.keys())
       ct = data_cntry[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           ct = ct*100
    else:
       ct = 'N/A'
    if data_field:
       fd = data_field[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           fd = fd*100
    else:
       fd = 'N/A'
    if data_inst:
       ins = data_inst[f'{prefix}_{year}'][metric][idx]
       if metric == 'self%':
           ins = ins*100
    else:
       ins = 'N/A'
    return {'own': str(r2dec(own)),'cntry': str(r2dec(ct)), 'field': str(r2dec(fd)), 'inst': str(r2dec(ins))}

def update_yr_options(career):
    if career == False:
        return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", 'disabled': True}, {"label": "2019", "value": 1, 'disabled': False}, 
        {"label": "2020", "value": 2, 'disabled': False}, {"label": "2021", "value": 3, 'disabled': False}, ]
    else: # career == True or None
        return [{"label": "2017", "value": 0, 'disabled': False}, {"label": "2018", "value": 1, 'disabled': False}, {"label": "2019", "value": 2, 'disabled': False}, 
        {"label": "2020", "value": 3, 'disabled': False}, {"label": "2021", "value": 4, 'disabled': False}]
def update_cr_options(avail):
    if avail == 'both':
        return [{"label": "Career", "value": True}, {"label": "Single year", "value": False}]
    elif avail == 'career':
        return [{"label": "Career", "value": True, 'disabled': True}, {"label": "Single year", "value": False, 'disabled': True}]
    elif avail == 'singleyr':
        return [{"label": "Career", "value": False,'disabled': True}, {"label": "Single year", "value": True, 'disabled': True}]

def update_auth_yrs(keys):
    opts = []
    for key in keys:
        if key.split('_')[-1] != "log":
            opts.append({"label": key.split('_')[-1], "value": key.split('_')[-1]})
    return opts
    
def load_standardized_data(root_data = 'data/'):

    # =============== Reading in the data

    maxlog_metrics = ['nc', 'h', 'hm',  'ncs', 'ncsf','ncsfl', 'nc (ns)', 'h (ns)', 'hm (ns)',  'ncs (ns)', 'ncsf (ns)','ncsfl (ns)']

    # === 2017 data
    data_path = root_data + 'version-1/'
    df_career_v1_2017 = pd.read_pickle(data_path + 'Table-S1-career-2017.pkl')
    df_career_v1_2017_log = pd.read_pickle(data_path + 'Table-S1-career-2017_LogTransform.pkl')
    df_singleyr_v1_2017 = pd.read_pickle(data_path + 'Table-S2-singleyr-2017.pkl')
    df_singleyr_v1_2017_log = pd.read_pickle(data_path + 'Table-S2-singleyr-2017_LogTransform.pkl')
    # standardize col names
    df_career_v1_2017, df_career_v1_2017_text = standardize_col_names(df = df_career_v1_2017, year = 2017, v1_present = True, singleyr = False)
    df_career_v1_2017_log, _ = standardize_col_names(df = df_career_v1_2017_log, year = 2017, v1_present = True, singleyr = False)
    df_singleyr_v1_2017, df_singleyr_v1_2017_text = standardize_col_names(df = df_singleyr_v1_2017, year = 2017, v1_present = True, singleyr = True)
    df_singleyr_v1_2017_log, _ = standardize_col_names(df = df_singleyr_v1_2017_log, year = 2017, v1_present = True, singleyr = True)

    # === 2018 data (only career data available!)
    df_career_v1_2018 = pd.read_pickle(data_path + 'Table-S4-career-2018.pkl')
    df_career_v1_2018_log = pd.read_pickle(data_path + 'Table-S4-career-2018_LogTransform.pkl')
    # standardize col names
    df_career_v1_2018, df_career_v1_2018_text = standardize_col_names(df = df_career_v1_2018, year = 2018, v1_present = True, singleyr = False)
    df_career_v1_2018_log, _ = standardize_col_names(df = df_career_v1_2018_log, year = 2018, v1_present = True, singleyr = False)

    # === 2019 data
    data_path = root_data + 'version-2/'
    df_career_v2_2019 = pd.read_pickle(data_path + 'Table-S6-career-2019.pkl')
    df_career_v2_2019_log = pd.read_pickle(data_path + 'Table-S6-career-2019_LogTransform.pkl')
    df_singleyr_v2_2019 = pd.read_pickle(data_path + 'Table-S7-singleyr-2019.pkl')
    df_singleyr_v2_2019_log = pd.read_pickle(data_path + 'Table-S7-singleyr-2019_LogTransform.pkl')
    # standardize col names
    df_career_v2_2019, df_career_v2_2019_text = standardize_col_names(df = df_career_v2_2019, year = 2019, v1_present = True, singleyr = False)
    df_career_v2_2019_log, _ = standardize_col_names(df = df_career_v2_2019_log, year = 2019, v1_present = True, singleyr = False)
    df_singleyr_v2_2019, df_singleyr_v2_2019_text = standardize_col_names(df = df_singleyr_v2_2019, year = 2019, v1_present = True, singleyr = True)
    df_singleyr_v2_2019_log, _ = standardize_col_names(df = df_singleyr_v2_2019_log, year = 2019, v1_present = True, singleyr = True)

    # === 2020 data
    data_path = root_data + 'version-3/'
    df_career_v3_2020 = pd.read_pickle(data_path + 'Table_1_Authors_career_2020_wopp_extracted_202108.pkl')
    df_career_v3_2020_log = pd.read_pickle(data_path + 'Table_1_Authors_career_2020_wopp_extracted_202108_LogTransform.pkl')
    df_singleyr_v3_2020 = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2020_wopp_extracted_202108.pkl')
    df_singleyr_v3_2020_log = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2020_wopp_extracted_202108_LogTransform.pkl')
    # standardize col names
    df_career_v3_2020, df_career_v3_2020_text = standardize_col_names(df = df_career_v3_2020, year = 2020, v1_present = True, singleyr = False)
    df_career_v3_2020_log, _ = standardize_col_names(df = df_career_v3_2020_log, year = 2020, v1_present = True, singleyr = False)
    df_singleyr_v3_2020, df_singleyr_v3_2020_text = standardize_col_names(df = df_singleyr_v3_2020, year = 2020, v1_present = True, singleyr = True)
    df_singleyr_v3_2020_log, _ = standardize_col_names(df = df_singleyr_v3_2020_log, year = 2020, v1_present = True, singleyr = True)

    # === 2021 data
    data_path = root_data + 'version-5/'
    df_career_v5_2021 = pd.read_pickle(data_path + 'Table_1_Authors_career_2021_pubs_since_1788_wopp_extracted_202209b.pkl')
    df_career_v5_2021_log = pd.read_pickle(data_path + 'Table_1_Authors_career_2021_pubs_since_1788_wopp_extracted_202209b_LogTransform.pkl')
    df_singleyr_v5_2021 = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2021_pubs_since_1788_wopp_extracted_202209b.pkl')
    df_singleyr_v5_2021_log = pd.read_pickle(data_path + 'Table_1_Authors_singleyr_2021_pubs_since_1788_wopp_extracted_202209b_LogTransform.pkl')
    # standardize col names
    df_career_v5_2021, df_career_v5_2021_text = standardize_col_names(df = df_career_v5_2021, year = 2021, v1_present = True, singleyr = False)
    df_career_v5_2021_log, _ = standardize_col_names(df = df_career_v5_2021_log, year = 2021, v1_present = True, singleyr = False)
    df_singleyr_v5_2021, df_singleyr_v5_2021_text = standardize_col_names(df = df_singleyr_v5_2021, year = 2021, v1_present = True, singleyr = True)
    df_singleyr_v5_2021_log, _ = standardize_col_names(df = df_singleyr_v5_2021_log, year = 2021, v1_present = True, singleyr = True)

    # =============== Save list of df names and attributes
    dfs_career = [df_career_v1_2017, df_career_v1_2018, df_career_v2_2019, df_career_v3_2020, df_career_v5_2021] ### DELETE: dfs = [df1,df2,df3,df5,df5_career] 
    dfs_singleyr = [df_singleyr_v1_2017, df_singleyr_v2_2019, df_singleyr_v3_2020, df_singleyr_v5_2021]

    dfs_career_log = [df_career_v1_2017_log, df_career_v1_2018_log, df_career_v2_2019_log, df_career_v3_2020_log, df_career_v5_2021_log] ### DELETE: dfs_log = [df1_log,df2_log,df3_log,df5_log,df5_career_log]
    dfs_singleyr_log = [df_singleyr_v1_2017_log, df_singleyr_v2_2019_log, df_singleyr_v3_2020_log, df_singleyr_v5_2021_log]

    dfs_career_text = [df_career_v1_2017_text, df_career_v1_2018_text, df_career_v2_2019_text, df_career_v3_2020_text, df_career_v5_2021_text] ### DELETE: text = [df1_text,df2_text,df3_text,df5_text,df5_career_text]
    dfs_singleyr_text = [df_singleyr_v1_2017_text, df_singleyr_v2_2019_text, df_singleyr_v3_2020_text, df_singleyr_v5_2021_text]
    ### DELETE: names = ['df1','df2','df3','df5','df5_career']

    dfs_career_yrs = [2017, 2018, 2019, 2020, 2021]
    dfs_singleyr_yrs = [2017, 2019, 2020, 2021]

    return(dfs_career, dfs_singleyr, dfs_career_log, dfs_singleyr_log, dfs_career_text, dfs_singleyr_text, dfs_career_yrs, dfs_singleyr_yrs)

# Quickly search a df for an author
def search_df(df,search_str,datatype = 'author'):
	if datatype == 'author':
	    tmp = df[df['authfull'].str.contains(search_str,na = False)]
	    for i in tmp.index:
	        print(f"Author {tmp.loc[i,'authfull']} ranks {tmp.loc[i,'rank (ns)']} (rank {tmp.loc[i,'rank']} with self-citation) out of {df.shape[0]}")
	if datatype == 'country':
	    tmp = df[df['cntry'].str.contains(search_str,na = False)]
	    print(f"{tmp.shape[0]} out of {df.shape[0]} authors come from {search_str}, and rank an average of {int(tmp['rank (ns)'].mean())} ({int(tmp['rank (ns)'].mean())} with self-citation). Their average % self-citation is {int(tmp['self%'].mean()*100)}% relative to a total mean of {int(df['self%'].mean()*100)}%.")
	if datatype == 'institution':
	    tmp = df[df['inst_name'].str.contains(search_str)]
	    print(f"{tmp.shape[0]} out of {df.shape[0]} authors come from {search_str}, and rank an average of {int(tmp['rank (ns)'].mean())} ({int(tmp['rank (ns)'].mean())} with self-citation). Their average % self-citation is {int(tmp['self%'].mean()*100)}% relative to a total mean of {int(df['self%'].mean()*100)}%.")

# standardize columns across datasest versions (1,2,3,5) and types (single year, career)
def standardize_col_names(df, year, v1_present = False, singleyr = False):
    generic_cols = ['authfull', 'inst_name', 'cntry', 'np', 'firstyr', 'lastyr','rank (ns)', 'nc (ns)', 'h (ns)', 'hm (ns)', 'nps (ns)','ncs (ns)', 'cpsf (ns)', 
                  'ncsf (ns)', 'npsfl (ns)', 'ncsfl (ns)','c (ns)', 'npciting (ns)', 'cprat (ns)', 'np cited (ns)','self%', 'rank', 'nc', 'h', 'hm', 
                  'nps', 'ncs', 'cpsf', 'ncsf','npsfl', 'ncsfl', 'c', 'npciting', 'cprat', 'np cited','np_d', 'nc_d', 'sm-subfield-1', 'sm-subfield-1-frac',
                  'sm-subfield-2', 'sm-subfield-2-frac', 'sm-field', 'sm-field-frac','rank sm-subfield-1', 'rank sm-subfield-1 (ns)', 'sm-subfield-1 count']
    generic_cols_text = [f'author name',f'institution name (large institutions only)',f'country associated with most recent institution',f'number of papers from 1960 to {year})',
                       f'year of first publication',f'year of most recent publication',f'rank based on composite score c',f'total cites from 1996 to {year}',
                       f'h-index as of the end of {year}',f'hm-index as of end-{year}',f'number of single authored papers',f'total cites to single authored papers',
                       f'number of single + first authored papers',f'total cites to single + first authored papers',f'number of single + first + last authored papers',
                       f'total cites to single + first + last authored papers',f'composite score',f'number of distinct citing papers',
                       f'ratio of total citations to distinct citing papers',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
                       f'self-citation percentage',f'rank based on composite score c',f'total cites 1996-{year}',f'h-index as of end-{year}',
                       f'hm-index as of end-{year}',f'number of single authored papers',f'total cites to single authored papers',
                       f'number of single + first authored papers',f'total cites to single + first authored papers',f'number of single + first + last authored papers',
                       f'total cites to single + first + last authored papers',f'composite score',f'number of distinct citing papers',
                       f'ratio of total citations to distinct citing papers',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',
                       f'# papers 1960-{year} in titles that are discontinued in Scopus',f'total cites 1996-{year} from titles that are discontinued in Scopus',
                       f'top ranked Science-Metrix category (subfield) for author',f'associated category fraction',f'second ranked Science-Metrix category (subfield) for author',
                       f'associated category fraction',f'top ranked higher-level Science-Metrix category (field) for author',
                       f'associated category fraction',f'rank of c within category sm-subfield-1',f'rank of c (ns) within category sm-subfield-1',
                       f'total number of authors within category sm-subfield-1']
    if not v1_present: 
        df.columns = generic_cols
        return(df,dict(zip(generic_cols, generic_cols_text))) # len(generic_cols_text) = 46
    else:
        remove_cols = ['np cited (ns)','np cited','np_d','nc_d','rank sm-subfield-1','rank sm-subfield-1 (ns)','sm-subfield-1 count']
        remove_text = [f'number of papers 1960-{year} that have been cited at least once (1996-{year})',f'number of papers 1960-{year} that have been cited at least once (1996-{year})',f'# papers 1960-{year} in titles that are discontinued in Scopus',f'total cites 1996-{year} from titles that are discontinued in Scopus',f'rank of c within category sm-subfield-1',f'rank of c (ns) within category sm-subfield-1',f'total number of authors within category sm-subfield-1']

        if year == 2017 or year == 2018:
            df = df.drop(columns = ['sm-1', 'sm-2','sm22'])
            if singleyr and year == 2017: # singleyr 2017 missing 2 columns!
                remove_cols += 'firstyr','lastyr' 
                remove_text += f'year of first publication',f'year of most recent publication'
            for item in remove_cols: generic_cols.remove(item)
            for item in remove_text: generic_cols_text.remove(item)
            df.columns = generic_cols
        else:
            df.columns = generic_cols
            for item in remove_cols: generic_cols.remove(item)
            for item in remove_text: generic_cols_text.remove(item)
            df = df.drop(columns = remove_cols)
        return(df,dict(zip(generic_cols, generic_cols_text))) # len(generic_cols_text) = 39 (37 for singleyr 2017)

def gen_dist_from_summary(sum_vec, N):
    data_size = N
    data = np.concatenate([
        np.random.uniform(sum_vec[0], sum_vec[1], data_size // 4),
        np.random.uniform(sum_vec[1], sum_vec[2], data_size // 4),
        np.random.uniform(sum_vec[2], sum_vec[3], data_size // 4),
        np.random.uniform(sum_vec[3], sum_vec[4], data_size // 4)
    ])
    return data


def get_violin_compare(fig, in1,in2,color1,color2,name,group_num):
    # The last entry is number of samples
    N1 = in1[5]
    N2 = in2[5]
    data1 = gen_dist_from_summary(in1, N1)
    data2 = gen_dist_from_summary(in2, N2)
    if N1>N2:
        N1 = int(10*(N1/N2))
        if N1>50:
            N1 = 50
        N2 = 10
    elif N2>N1:
        N2 = int(10*(N2/N1))
        if N2>50:
            N2 = 50
        N1 = 10
    fig.add_trace(go.Violin(
        y=data1,
        box_visible=False,
        fillcolor=color1[0],
        #fillcolor='rgba(0, 255, 0, 0.5)',
        side='positive',
        hoverinfo='text+y',
        #legendgroup='M',
        name = name
    ), row = 1, col = group_num)
    fig.add_trace(go.Violin(
        y=data2,
        box_visible=False,
        fillcolor=color2[0],
        side='negative',
        hoverinfo='text+y',
        #legendgroup='M',
        name = name
    ), row = 1, col = group_num)
    # Update layout for better visibility
    fig.update_traces(meanline_visible=True,
                      points= False, # show all points
                      jitter=0.05,  # add some jitter on points for better visibility
                      scalemode='width'
                     )
    fig.update_layout(violingap=0, violinmode='overlay', showlegend=False)
    
    # Show the plot
    return fig