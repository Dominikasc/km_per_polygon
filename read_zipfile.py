# -*- coding: utf-8 -*-
"""
Created on Tue Apr 20 09:13:18 2021
Modified on Mon Jun 19 2023

@author: santi
@coauthor: dominika

"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
import math

import shapely #NEW
from shapely.geometry import LineString
from shapely.geometry import Point #NEW
import pyproj #NEW

import itertools
import base64
import string #NEW
from string import ascii_uppercase #NEW
#from glob import iglob
#import glob

st.set_page_config(layout="wide")
st.sidebar.header('Drag and drop files here')
uploaded_files = st.sidebar.file_uploader('Upload routes.txt, trips.txt, stop_times.txt, calendar.txt, shapes.txt and polygons.geojson', accept_multiple_files=True, type=['txt','geojson'])

# Get the polygons
# polys = gpd.read_file("https://raw.githubusercontent.com/Dominikasc/km_per_polygon/main/data/polygons.geojson")
# polys = gpd.read_file(next(iglob('*.csv')))
# polylist = glob.glob("*.geojson")  # Get all geojson files in the current folder

# pli = []

# for filename in polylist:
#     pf = gpd.read_file(filename)
#     pli.append(pf)

# polys = gpd.GeoDataFrame(pd.concat(pli, ignore_index=True))
# polys = polys.to_crs(epsg=4326)


# get files
# Upload files from GTFS
if uploaded_files != []:
    for file in uploaded_files:
        name = file.name
        
        # Parse the files of the GTFS I need
        if name=='routes.txt':
            routes = pd.read_csv(file)
            if len(routes.route_short_name.unique()) == 1:
                routes['route_short_name'] = routes['route_long_name']
                
        elif name == 'trips.txt':
            trips = pd.read_csv(file)
        elif name == 'stop_times.txt':
            stop_times = pd.read_csv(file)  
        elif name == 'calendar.txt':
            calendar = pd.read_csv(file)
        elif name == 'shapes.txt':
            aux = pd.read_csv(file)
            aux.sort_values(by=['shape_id', 'shape_pt_sequence'], ascending=True, inplace=True)
            aux = gpd.GeoDataFrame(data=aux[['shape_id']], geometry = gpd.points_from_xy(x = aux.shape_pt_lon, y=aux.shape_pt_lat))
            lines = [LineString(list(aux.loc[aux.shape_id==s, 'geometry']))  for s in aux.shape_id.unique()]
            shapes = gpd.GeoDataFrame(data=aux.shape_id.unique(), geometry = lines, columns = ['shape_id'])
        elif name == 'polygons.geojson':     # Get the polygons, need to be uploaded as Geojson, not sure if this works
            polys = gpd.read_file(file)
            polys = polys.to_crs(epsg=4326)

    # Define number of days
    # Define number of days

    weekday = st.sidebar.number_input('Insert number of weekdays', value=251)
    saturday = st.sidebar.number_input('Insert number of saturdays', value=52)
    sunday = st.sidebar.number_input('Insert number of sundays', value=62)
    
    #weekday=251
    #saturday=52
    #sunday =62
    
    # I need the route_id in stop_times
    stop_times = pd.merge(stop_times, trips, how='left')
    
    # I need the route_short_name in trips
    trips = pd.merge(trips, routes[['route_id', 'route_short_name']])
    
    # I need the start and end coordinate in shapes

    def startcoord(row):
        first = Point(row['geometry'].coords[0])
        return first

    def endcoord(row):
        last = Point(row['geometry'].coords[-1])
        return last

    shapes['startcoord'] = shapes.apply(lambda row: startcoord(row), axis=1)
    shapes['endcoord'] = shapes.apply(lambda row: endcoord(row), axis=1)

    # I need the intersection and also to keep the shape_id and poly_id or index
    # Get the intersection betwee each shape and each polygon
    intersection_geo = [s.intersection(p) for s in shapes.geometry for p in polys.geometry]
    intersection = gpd.GeoDataFrame(geometry=intersection_geo)
    intersection.crs = {'init':'epsg:4326'}
    
    
    # Get the shape_ids repeated as many times as polygons there are
    shape_ids = [[s]*len(polys) for s in shapes.shape_id]
    
    # Get the polygon list as many times as shapes there are
    poly_index = [list(polys.index) for s in shapes.shape_id]
    
    # Add shape_id and polygon index to my intersection gdf
    intersection['shape_id'] = list(itertools.chain.from_iterable(shape_ids))
    # intersection['shape_id']  = intersection['shape_id']  + 'a' #this is only for keplergl to show it right
    intersection['poly_index'] = list(itertools.chain.from_iterable(poly_index))
    
    # Keep only the ones that intersected
    intersection = intersection.loc[~intersection.geometry.is_empty].reset_index()
    
    # Calculate the length of the intersection in km
    intersection['km_in_poly'] = intersection.geometry.to_crs(3587).length/1000  # changed from 32632 to 3587
    intersection['miles_in_poly'] = intersection['km_in_poly']*0.621371
    

    # Add the number of days per year 

    calendar.loc[calendar['monday']>0, 'days_per_year'] = weekday
    calendar.loc[calendar['saturday']>0, 'days_per_year'] = saturday
    calendar.loc[calendar['sunday']>0, 'days_per_year'] = sunday

    # Get the patters with the same criteria as Remix
    # Pattern A is the one with more trips
    # If two patterns have the same number of trips, then the longer
    
    # Number of trips per shape
    trips_per_shape0 = trips.pivot_table('trip_id', index=['route_id', 'shape_id','direction_id','service_id'], aggfunc='count').reset_index()
    trips_per_shape0.rename(columns = dict(trip_id = 'ntrips'), inplace=True)
    shapes.crs = {'init':'epsg:4326'}
    shapes['length_m'] = shapes.geometry.to_crs(epsg=3587).length # Changed from 4326 # CRS.from_epsg() --> deprecation warning

    trips_per_shape = pd.merge(trips_per_shape0, calendar[['service_id','days_per_year']], how='left')
    trips_per_shape['trips_per_year'] = trips_per_shape['ntrips']*trips_per_shape['days_per_year']

   
    trips_per_shape = trips_per_shape.groupby(['route_id','shape_id','direction_id']).aggregate({'service_id':lambda x: list(x),'ntrips':'sum','trips_per_year':'sum'}).reset_index() # added service_id
    trips_per_shape =  pd.merge(trips_per_shape, shapes[['shape_id']], how='left') # added start/end coordinates

    # Number of stops per shape
    aux = stop_times[['route_id', 'stop_id', 'stop_sequence', 'trip_id', 'shape_id','shape_dist_traveled']] # No need to merge with trips, data already merged in line 66
    aux1 = aux.groupby(['route_id', 'trip_id','shape_id'])['shape_dist_traveled'].max().reset_index() # add shapes_dist_travelled for accurate km in pattern sorting
    aux1 = pd.merge(aux[['route_id', 'stop_id', 'stop_sequence', 'trip_id', 'shape_id']], aux1[['route_id', 'trip_id','shape_id','shape_dist_traveled']], left_on=['route_id','trip_id','shape_id'],right_on=['route_id','trip_id','shape_id'], how='left')
    aux1 = aux1.drop_duplicates(subset=['shape_id', 'stop_sequence']).drop('trip_id', axis=1).sort_values(by=['route_id', 'shape_id', 'stop_sequence'], ascending=True).reset_index() # Removed route_id from subset to get accurate nb of stops

    # Get stops per shape

    stops_per_shape = aux1.groupby('shape_id').aggregate({'stop_sequence':'count','shape_dist_traveled':'max'}).reset_index()
    stops_per_shape.rename(columns = dict(stop_sequence = 'nstops', shape_dist_traveled = 'pattern_dist' ), inplace=True)
    stops_per_shape.pattern_dist = stops_per_shape.pattern_dist/1000
    
    
    # Get all the variables I need to assign patterns in the same df
    patterns = pd.merge(trips_per_shape, shapes.drop('geometry', axis=1), how='left').sort_values(by=['route_id', 'ntrips', 'length_m'], ascending=False)
    patterns = pd.merge(patterns, stops_per_shape, how='left')
    patterns = pd.merge(routes[['route_id', 'route_short_name']], patterns, how='left')
    
    # Manage directions
    direction_0 = patterns.loc[patterns.direction_id == 0].reset_index().drop('index', axis=1)
    direction_1 = patterns.loc[patterns.direction_id == 1].reset_index().drop('index', axis=1)
    
    # Haversine formula

    def distancehav(point1, point2):
        dLat = math.radians(point2.y) - math.radians(point1.y)
        dLon = math.radians(point2.x) - math.radians(point1.x)
        a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(math.radians(point1.y)) * math.cos(math.radians(point2.y)) * math.sin(dLon/2) * math.sin(dLon/2)
        distance = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = distance * 1000
        return distance

    # Assign patterns - 
    # These are meant to match shapes in opposite directions under the same pattern 
    # But they are not the final pattern name
    # 1. whether the start & end locations exactly match (i.e. does the inbound direction end at the start of the outbound direction, and vice versa)
    # 2. whether the start & end locations are within 400m of each other
    # 3. the difference in the number of trips on each day of service

    assigned_patterns = pd.DataFrame()

    for r in patterns.route_short_name.unique():
        t0 = direction_0.loc[direction_0.route_short_name==r]
        t1 = direction_1.loc[direction_1.route_short_name==r]
    
        if len(t0) >= len(t1):
            longer = t0.reset_index()
            shorter = t1.reset_index()
        else:
            longer = t1.reset_index()
            shorter = t0.reset_index()
    
        ABC = list(ascii_uppercase) + [letter1+letter2 for letter1 in ascii_uppercase for letter2 in ascii_uppercase]

        longer['aux_pattern'] = ''
        shorter['aux_pattern'] = ''
    
        for i in range(len(longer)):
            longer.loc[i, 'aux_pattern'] = ABC[i]
            nstops = longer.iloc[i]['nstops']
            start_longer = longer.iloc[i]['startcoord']
            end_longer = longer.iloc[i]['endcoord']
            servicedays_longer = longer.iloc[i]['service_id']
    
            for j in range(len(shorter)):
                start_shorter = shorter.iloc[j]['startcoord']
                end_shorter = shorter.iloc[j]['endcoord']
                servicedays_shorter = shorter.iloc[j]['service_id']
                condition_start = distancehav(start_shorter, end_longer) <= 400
                condition_end = distancehav(start_longer, end_shorter) <= 400
                some_days_in_common = len([id for id in servicedays_longer if id in servicedays_shorter])>0
                condition3 = nstops*0.95 <= shorter.iloc[j]['nstops'] <= nstops*1.05

                if condition_start & condition_end & some_days_in_common & condition3: 
                    shorter.loc[j, 'aux_pattern'] = ABC[i]
                elif shorter.loc[j, 'aux_pattern'] == "":
                    shorter.loc[j, 'aux_pattern'] = ABC[-i] # to assign a pattern for all unmatched
                    break

        assigned_patterns = pd.concat([assigned_patterns,longer])
        assigned_patterns = pd.concat([assigned_patterns,shorter])
        assigned_patterns.drop('index', inplace=True, axis=1)


    # Intersection geometries I need
    intersection1 = pd.merge(intersection, polys[['NAME']], left_on='poly_index', right_on=polys.index, how='left')
    intersection1 = gpd.GeoDataFrame(data = intersection1.drop(['index','poly_index','geometry'], axis=1), geometry = intersection1.geometry)
    
    # Get actual number of stops, trips, trips per year and pattern distance
    assigned_patterns3 = assigned_patterns.groupby(['route_id', 'route_short_name','aux_pattern']).aggregate({'nstops':'sum','pattern_dist':'sum','ntrips':'sum','trips_per_year':'sum',}).reset_index()
    assigned_patterns = pd.merge(assigned_patterns.loc[:, ~assigned_patterns.columns.isin(['index','nstops','pattern_dist','ntrips','trips_per_year'])],assigned_patterns3,how='left').reset_index().sort_values(['route_short_name'])

    # Merge all variables
    assigned_patterns1 = pd.merge(assigned_patterns[['route_short_name', 'shape_id','aux_pattern', 'ntrips','trips_per_year','nstops','pattern_dist']], intersection1, how='right') # Added trips per year
    assigned_patterns1['km_per_year'] = assigned_patterns1.km_in_poly * assigned_patterns1.trips_per_year     # Add km per year

    assigned_patterns2 = assigned_patterns1.groupby(['route_short_name', 'aux_pattern']).aggregate({'nstops':'max','ntrips':'max','km_in_poly':'sum','km_per_year':'sum','pattern_dist':'max'}).reset_index().sort_values(by = ['route_short_name','ntrips'], ascending=False) # New
    assigned_patterns2.reset_index(inplace=True)
    assigned_patterns2.drop('index', axis=1, inplace=True)
    
    # Assigned patterns depending on the total trips for both directions combined
    for r in assigned_patterns2.route_short_name.unique():
        aux = assigned_patterns2.loc[assigned_patterns2.route_short_name==r]
        pattern_list = list(ABC[0:len(aux)])
        assigned_patterns2.loc[assigned_patterns2.route_short_name==r, 'pattern'] = pattern_list

     # Merge dataframe with the real patterns and df with the municipalities
    df1 = assigned_patterns1[['route_short_name', 'aux_pattern', 'shape_id', 'NAME', 'km_in_poly','geometry','km_per_year']] # Added km_per_year
    df2 = assigned_patterns2[['route_short_name', 'aux_pattern', 'pattern']]
    
    # This is what I need to show the table
    # I have the fields to filter by route and county
    try_this = pd.merge(df1, df2, how='left')
    table = try_this.pivot_table(['km_in_poly','km_per_year'], index=['route_short_name', 'pattern', 'NAME'], aggfunc='sum').reset_index() # Added km_per_year
    table.rename(columns = dict(route_short_name = 'Route', NAME = 'County', pattern = 'Pattern', km_in_poly = 'Kilometers per county', km_per_year = 'Kilometers per year'), inplace=True)
    
    # This is what I need to draw the map
    # I have the fields to filter by route and county
    gdf_intersections = gpd.GeoDataFrame(data = assigned_patterns1[['route_short_name', 'pattern', 'NAME']], geometry = assigned_patterns1.geometry)
    gdf_intersections.rename(columns = dict(route_short_name = 'Route', NAME = 'County', pattern = 'Pattern'), inplace=True)
    
    # -------------------------------------------------------------------------------
    # --------------------------- APP -----------------------------------------------
    # -------------------------------------------------------------------------------
    # LAYING OUT THE TOP SECTION OF THE APP
    st.header("Bus kilometers per county (geographical boundary)")
    # LAYING OUT THE MIDDLE SECTION OF THE APP WITH THE MAPS
    col1, col2, col3= st.columns((1, 2 ,3))
        
    # Select filters
    poly_names_list = list(gdf_intersections['County'].unique())
    lines_names_list = list(gdf_intersections['Route'].unique())
    lines_names_list = [str(x) for x in lines_names_list]

    poly_names_list.sort()
    lines_names_list.sort()
    
    with col1:
        st.subheader('Filters')
        filter_polys = st.multiselect('Counties', poly_names_list)
        filter_routes = st.multiselect('Routes', lines_names_list)
        st.subheader('Pivot dimensions')
        group_by = st.multiselect('Group by', ['County', 'Route', 'Pattern'], default = ['County', 'Route', 'Pattern'])
        
    if filter_polys == []:
        filter_polys = poly_names_list
        
    if filter_routes == []:
        filter_routes = lines_names_list
        
    # Work for the datatable
    # Aggregate data as indicated in Pivot dimensions    
    # Filter data
    table_poly = table.loc[
        (table['Route'].isin(filter_routes))&
        (table['County'].isin(filter_polys))
        ]
    table_poly = table_poly.pivot_table(['Kilometers per county','Kilometers per year'], index=group_by, aggfunc='sum').reset_index() # Added km_per_year

    table_poly['Kilometers per county'] = table_poly['Kilometers per county'].apply(lambda x: str(round(x, 2)))     
    table_poly['Kilometers per year'] = table_poly['Kilometers per year'].apply(lambda x: str(round(x, 2)))     

                
    # Filter polygons that passed the filter
    # Merge the intersection with the number of trips per shape
    intersection_aux = pd.merge(trips, intersection1, how='right')
    intersection2 = intersection_aux.drop_duplicates(subset=['route_short_name', 'NAME','pattern']).loc[:,['route_short_name', 'NAME','pattern']].reset_index()
    
    # Add polygons geometries
    intersection2 = pd.merge(intersection2, polys, left_on='NAME', right_on='NAME', how='left')
    
    # This is what I need to select the polygons that passed the route and county filters
    route_polys = gpd.GeoDataFrame(data=intersection2[['route_short_name', 'NAME']], geometry=intersection2.geometry)
    
    filtered = route_polys.loc[
        (route_polys['NAME'].isin(filter_polys))&
        (route_polys.route_short_name.isin(filter_routes))
        ]
        
    # Filter line intersections that passed the filters
    line_intersections = gdf_intersections.loc[
        (gdf_intersections['Route'].isin(filter_routes))&
        (gdf_intersections['County'].isin(filter_polys))
        ].__geo_interface__
    
    # Assign color to patterns
    color_lookup = pdk.data_utils.assign_random_colors(line_intersections['Pattern'])
    
    # Filter the shapes that passed the routes filters
    aux = trips.drop_duplicates(subset=['route_id', 'shape_id'])
    aux = pd.merge(aux, routes[['route_id', 'route_short_name']], how='left')
    shapes_filtered = pd.merge(shapes ,aux, how='left')
    shapes_filtered = gpd.GeoDataFrame(data = shapes_filtered.drop('geometry', axis=1), geometry=shapes_filtered.geometry)
    shapes_filtered = shapes_filtered.loc[shapes_filtered.route_short_name.isin(filter_routes)]
    
    # Calculate the center
    avg_lon = polys.geometry.centroid.x.mean()
    avg_lat = polys.geometry.centroid.y.mean()    

    with col2:
        st.subheader('Total km per county = {}'.format(round(table_poly['Kilometers per county'].map(float).sum(),1)))
                    # Download data
        def get_table_download_link(df):
            """Generates a link allowing the data in a given panda dataframe to be downloaded
            in:  dataframe
            out: href string
            """
            csv = df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()  # some strings <-> bytes conversions necessary here
            href = f'<a href="data:file/csv;base64,{b64}">Download csv file</a>'
            return href
        
        st.dataframe(table_poly, 900, 600)
        st.markdown(get_table_download_link(table_poly), unsafe_allow_html=True)
      
    with col3: 
        # CREATE THE MAP
        st.subheader('Map')
        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            # api_keys =  MAPBOX_API_KEY,
            initial_view_state={
                "latitude": avg_lat,
                "longitude": avg_lon,
                "zoom": 11,
                "pitch": 0,
                "height":600,
            },
            layers = [
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=filtered, 
                    # stroked = True,
                    # filled = False,
                    opacity=0.4,
                    get_fill_color= [220, 230, 245],#[150, 150, 150], #'[properties.weight * 255, properties.weight * 255, 255]',#
                    get_line_color= [255, 255, 255],
                    get_line_width = 30,
                    pickable=False,
                    extruded=False,
                    converage=1
                    ),
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=shapes_filtered, 
                    # get_fill_color=[231,51,55],
                    get_line_color=[212, 174, 174],#[50,50,50],
                    opacity=.8,
                    pickable=False,
                    extruded=True,
                    converage=1,
                    filled= True,
                    line_width_scale= 20,
                    line_width_min_pixels= 2,
                    get_line_width = 1,
                    get_radius = 100,
                    get_elevation= 30             
                    ),
                pdk.Layer(
                    "GeoJsonLayer", 
                    data=line_intersections, 
                    #get_fill_color=[231,51,55],
                    get_line_color = [200,51,55],
                    opacity=1,
                    pickable=False,
                    extruded=False,
                    converage=1,
                    filled= True,
                    line_width_scale= 20,
                    line_width_min_pixels= 2,
                    get_line_width = 1,
                    get_radius = 100,
                    get_elevation= 30             
                    )
                ]
        ))
        
