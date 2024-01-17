
# =============================================
# IMPORT LIBRARIES
# =============================================

import numpy as np
import pandas as pd
import json
import pickle

import plotly.graph_objects as go
from IPython.core.display import display, HTML
from plotly.offline import plot
import plotly.express as px
from plotly.subplots import make_subplots
import country_converter as coco
from citations_lib.utils import *

# =============================================
# Color formatting
# =============================================

darkAccent1 = '#2C2C2C' # dark gray
darkAccent2 = '#5b5959' # pale gray
darkAccent3 = '#CFCFCF' # almost white
lightAccent1 = '#ECAB4C' # ocre
highlight1 = 'lightsteelblue'
highlight2 = 'cornflowerblue'
theme =  {
    'dark': True,
    'detail': lightAccent1,
    'primary': darkAccent1,
    'secondary': lightAccent1
}

g1c = [highlight1, darkAccent2] # bar plot bars 1 & 2
g2c = [highlight2, darkAccent3] # bar plot bar 3
bgc = darkAccent1 # bar plot background

# =============================================
# FUNCTIONS
# =============================================

def update_c_and_rank(df_in, author, metrics_dict, ns = True, logTransf=False, weights = [1,1,1,1,1,1]):
    df = df_in.copy()
    c_metric = 'c (ns)' if ns else 'c'
    y_values = []
    y_values_prev = []

    # update composite score
    new_c = 0
    i = 0
    for key, val in metrics_dict.items(): 
        w_i = 6*(weights[0]/(np.array(weights).sum()))
        new_c += w_i*(np.log(metrics_dict[key] + 1) / np.log(df_in[key].max() + 1))
        y_values.append(np.log(metrics_dict[key] + 1) / np.log(df_in[key].max() + 1)) if logTransf else y_values.append(metrics_dict[key])
        y_values_prev.append(np.log(float(df_in[df_in['authfull'] == author][key].values) + 1)/ np.log(df_in[key].max() + 1)) if logTransf else y_values_prev.append(float(df_in[df_in['authfull'] == author][key].values))
        i += 1
    # update ranking
    df.iloc[int(df[df['authfull'] == author].index.values),df.columns.get_loc(c_metric)] = new_c
    df = df.sort_values(c_metric, ascending = False).reset_index()
    new_rank = int(df[df['authfull'] == author].index.values) + 1
    y_values.append(new_c) # important: do NOT log transform this!
    y_values_prev.append(float(df_in[df_in['authfull'] == author][c_metric].values))
    return new_c, new_rank, y_values, y_values_prev

def get_initial_metrics_list(df_in, author, ns = True):
    metrics_dict = {}
    all_metrics = ['nc', 'h', 'hm',  'ncs', 'ncsf','ncsfl','nc (ns)','h (ns)',
        'hm (ns)',  'ncs (ns)', 'ncsf (ns)','ncsfl (ns)']
    key_list = all_metrics[6:12] if ns else all_metrics[0:6]
    if author == None: 
        for key in key_list: metrics_dict[key] = 0 
    else: 
        try:
            for key in key_list: metrics_dict[key] = df_in[key]
        except:
            float(df_in[df_in['authfull'] == author][key].values)
    return(metrics_dict)

def create_geo_json(df_in, df_in_log,career, yr, metric, color_by = 'count',logTransf = False, empty = False):
    '''
    Heavily inspired by Thibaud Lamothe tutorial here: https://towardsdatascience.com/how-to-create-outstanding-custom-choropleth-maps-with-plotly-and-dash-49ac918a5f05
    data/custom.geo.json was generated here: https://geojson-maps.ash.ms/

    options for color_by: 
        'count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max', 'count_log', 'mean_log',
        'std_log', 'min_log', '25%_log', '50%_log', '75%_log', 'max_log'
    '''

    # === Creating country df ===
    cc = coco.CountryConverter()
    country_df = df_in.groupby('cntry')[metric].describe()
    country_df_log = df_in_log.groupby('cntry')[metric].describe()
    country_df_log.columns = [item + '_log' for item in country_df_log.columns]
    country_df = country_df.join(country_df_log)
    country_df['CODE'] = country_df.index #[i for i in country_df.index]
    if 'csk' in country_df.index: country_df = country_df.drop(['csk']) # Czekoslovakia – unclear if that uni is in Czech Republic or Slovakia!
    if 'nan' in country_df.index: country_df = country_df.drop(['nan'])
    names = []
    for cntry in list(country_df['CODE']):
        if str(cntry) == 'sux': names.append('Russia')
        elif str(cntry) == 'ant': names.append('Netherlands')
        elif str(cntry) == 'scg': names.append('Czech Republic')
        else: names.append(cc.convert(cntry, to = 'name_short'))
    country_df['COUNTRY'] = names
    country_df['GEOMETRY'] = ['']*len(country_df)

    # Loading geojson
    world_path = 'aggregate/custom.geo.json'
    with open(world_path) as f: geo_world = json.load(f)

    # Adding geometry to main df
    countries_geo = []
    for cntry in geo_world['features']:
        cntry_name = cntry['properties']['iso_a3'].lower()
        if cntry_name in country_df.index:
            geometry = cntry['geometry']
            countries_geo.append({'type': 'Feature', 'geometry': geometry, 'id':cntry_name})
    geo_world_ok = {'type': 'FeatureCollection', 'features': countries_geo}

    if empty or color_by == None: 
        fig = px.choropleth(geojson = geo_world_ok)
        geo_title = 'No dataset selected'
    else: 
        if logTransf and color_by != 'count' and metric != 'c' and metric != 'c (ns)': 
            fig = px.choropleth(country_df, geojson = geo_world_ok, locations = 'CODE', color = color_by + '_log', #labels = ['COUNTRY', color_by], range_color = [0, country_df[color_by + '_log'].max()],
                hover_data = ['COUNTRY', color_by])#hover_name = 'COUNTRY', #hover_data = color_by
                    #fig.update_layout(geo=dict(bgcolor= bgc), plot_bgcolor = bgc, paper_bgcolor = bgc, font = dict(color = lightAccent1), coloraxis_colorbar = dict(title = color_by.title(),
                    #tickvals = [k*(country_df[color_by + '_log'].max()/10) for k in range(0,10)],tickmode = 'array',nticks = 10, ticktext = [int(np.exp(k*(country_df[color_by + '_log'].max()/10)*(np.log(country_df[color_by].max() + 1)))) for k in range(0,10)]))
            geo_title = 'Log-Transformed ' + get_metric_long_name(career, yr, metric).title() + ' – ' + color_by.title() + ' By Country'
            
        else:
            fig = px.choropleth(country_df, geojson = geo_world_ok, locations = 'CODE', color = color_by, hover_name = 'COUNTRY')
            geo_title = get_metric_long_name(career, yr, metric).title() + ' – ' + color_by.title() + ' By Country'
        fig.update_layout(geo=dict(bgcolor= bgc), plot_bgcolor = bgc, paper_bgcolor = bgc, font = dict(color = lightAccent1), coloraxis_colorbar = dict(title = color_by.title()))
    return(fig, geo_title)