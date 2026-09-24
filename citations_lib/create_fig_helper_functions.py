# =============================================
# Color formatting
# =============================================

darkAccent2 = '#4A5670' # raised surface
lightAccent1 = '#00B4D8' # cyan leaf, primary accent
# Transparent, not a colour: the page's own background shows through, so
# a chart follows the light/dark switch without being redrawn.
bgc = 'rgba(0,0,0,0)' # chart background: inherit the page

# =============================================
# FUNCTIONS
# =============================================

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
