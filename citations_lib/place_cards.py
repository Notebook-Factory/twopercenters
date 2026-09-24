"""The cards the map opens: a place in a modal, a row of its list over the map.

Built from the same pieces as the Explore card (card_header, card_chips and
its classes), so a researcher looks the same wherever they are opened. Only
the stat tiles are new: the Explore card shows two ranks where these show
three or four plain counts.
"""
import urllib.parse

from dash import html

from citations_lib.auth_find import card_chips, card_header


def _edition(is_career, year):
    return f'Career, up to {year}' if is_career else f'Single year {year}'


def stat_tiles(tiles):
    """[(label, value, detail)] as a row of big numbers. A value that is not
    a number is shown as a dash rather than left out, so a row of tiles
    keeps its shape from one place to the next."""
    cells = []
    for label, value, detail in tiles:
        if isinstance(value, float) and not value.is_integer():
            shown = f'{value:,.2f}'
        elif isinstance(value, (int, float)):
            shown = f'{int(value):,}'
        else:
            shown = '-'
        cells.append(html.Div([
            html.Div(shown, className='ev-tile-value'),
            html.Div(label, className='ev-tile-label'),
            html.Div(detail or '', className='ev-tile-detail'),
        ], className='ev-tile'))
    return html.Div(cells, className='ev-tiles')


def _whole(value):
    """A median or percentile of a count, rounded to a count. The hm-index
    is fractional by construction and is left alone."""
    return round(value) if isinstance(value, (int, float)) else value


def _card(header, *body):
    return html.Div([html.Div(header, className='ev-id-head'), *body],
                    className='ev-id-card ev-place-card')


def notice_card(title, is_career, year, message):
    """A card with nothing to count: no record, or no statistic chosen."""
    return _card(card_header(title, None, None, None,
                             _edition(is_career, year)),
                 html.P(message, className='ev-place-note'))


# ------------------------------------------------------------- places

def city_card(where, region, country, place, is_career, year):
    """A city: what can be counted directly, since there is no aggregate
    for a city the way there is for a country."""
    header = card_header(where, None, ', '.join(p for p in (region, country)
                                                if p) or None, None,
                         _edition(is_career, year))
    return _card(header, stat_tiles([
        ('Researchers on the list', place['researchers'], None),
        ('Total citations', place['citations'], 'summed over its researchers'),
        ('Total papers', place['papers'], 'summed over its researchers'),
        ('Highest h-index', place['h'], None),
    ]))


def country_card(country, researchers, worldwide, statistic, summary,
                 stat_index, is_career, year):
    """A country: how many it has on the list, and the chosen statistic of
    four indicators across them."""
    header = card_header(country, None, None, None, _edition(is_career, year))
    detail = f'of {worldwide:,} worldwide' if worldwide else None
    tiles = [('Researchers on the list', researchers, detail)]
    if summary is not None:
        tiles += [
            ('Citations', _whole(summary['nc'][stat_index]), statistic),
            ('H-index', _whole(summary['h'][stat_index]), statistic),
            ('Hm-index', summary['hm'][stat_index], statistic),
        ]
    body = [stat_tiles(tiles)]
    if summary is not None:
        body.append(html.Div(card_chips(
            summary['self%'][stat_index] * 100, None), className='ev-id-chips'))
    return _card(header, *body)


# ------------------------------------------------------------- rows

def researcher_card(name, record, is_career, year):
    """One researcher, as the Explore card draws them, minus the ranks and
    the what-if: those are one click away in Explore itself."""
    header = card_header(name, record.get('inst_name'), record.get('cntry'),
                         record.get('sm-field'), _edition(is_career, year))
    return _card(header, stat_tiles([
        ('Citations', record.get('nc'), None),
        ('H-index', record.get('h'), None),
        ('Hm-index', record.get('hm'), 'adjusted for co-authorship'),
    ]), html.Div(card_chips((record.get('self%') or 0) * 100, None),
                 className='ev-id-chips'))


def institution_card(name, ror, summary, statistic, stat_index, is_career,
                     year):
    """One institution: how many of its researchers are on the list, and
    the chosen statistic across them. The city comes from ROR, when the
    institution was matched there."""
    header = card_header(name, None, (ror or {}).get('city'), None,
                         _edition(is_career, year))
    return _card(header, stat_tiles([
        ('Researchers on the list', summary['nc'][5], None),
        ('Citations', _whole(summary['nc'][stat_index]), statistic),
        ('H-index', _whole(summary['h'][stat_index]), statistic),
        ('Hm-index', summary['hm'][stat_index], statistic),
    ]))


# ------------------------------------------------------------- links

def _link(icon, label, href):
    return html.A([html.Span(className=f'ev-ic ev-ic-{icon}'),
                   html.Span(label)],
                  href=href, target='_blank', rel='noopener noreferrer',
                  className='ev-id-link')


def researcher_links(name, openalex_url):
    """OpenAlex only on a confident match (see utils.openalex_author); a
    Scholar search always, since a search makes no claim about who is who;
    and the way into Explore."""
    links = []
    if openalex_url:
        links.append(_link('external-link', 'OpenAlex', openalex_url))
    links.append(_link('external-link', 'Google Scholar',
                       'https://scholar.google.com/scholar?q='
                       + urllib.parse.quote(str(name))))
    links.append(html.Button(
        [html.Span(className='ev-ic ev-ic-target'),
         html.Span('Open in Explore')],
        id='row-card-explore', n_clicks=0, className='ev-share-btn'))
    return links


def institution_links(ror):
    if not ror or not ror.get('ror_id'):
        return []
    return [_link('external-link', 'ROR record', ror['ror_id'])]
