# -*- coding: utf-8 -*-
"""
Created on Tue Apr 20 09:13:18 2021
Last Modified on Mon Jan 29 2024

@author: santi
@coauthor: dominika

"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
from geopandas import GeoDataFrame 
import math
import numpy as np

import shapely 
from shapely.geometry import LineString
from shapely.geometry import Point 
from shapely import ops 

import pyproj

import itertools
import base64
import glob 
import string 
import rtree 
from string import ascii_uppercase 
import datetime 
import utm #new
import re #new
import sys #new
from st_aggrid import AgGrid, GridOptionsBuilder #NEW



#from glob import iglob
#import glob

st.set_page_config(layout="wide")
st.sidebar.header('Data Upload')
uploaded_files = st.sidebar.file_uploader('Please upload routes.txt, stops.txt, trips.txt, stop_times.txt, calendar.txt, shapes.txt and features.geojson from Remix.', accept_multiple_files=True, type=['txt','geojson'])

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
        elif name == 'stops.txt':
            stops = pd.read_csv(file)
        elif name == 'shapes.txt':
            aux = pd.read_csv(file)
            aux.sort_values(by=['shape_id', 'shape_pt_sequence'], ascending=True, inplace=True)
            aux = gpd.GeoDataFrame(data=aux[['shape_id']], geometry = gpd.points_from_xy(x = aux.shape_pt_lon, y=aux.shape_pt_lat))
            lines = [LineString(list(aux.loc[aux.shape_id==s, 'geometry']))  for s in aux.shape_id.unique()]
            shapes = gpd.GeoDataFrame(data=aux.shape_id.unique(), geometry = lines, columns = ['shape_id'])
        elif name == 'features.geojson':     # Get the polygons, need to be uploaded as Geojson, not sure if this works
            polys = gpd.read_file(file)
            polys = polys.to_crs(epsg=4326)

    # Define number of days
    monday = st.sidebar.number_input('Mondays', value=51)
    tuesday = st.sidebar.number_input('Tuesdays', value=51)
    wednesday = st.sidebar.number_input('Wednesdays', value=51)
    thursday = st.sidebar.number_input('Thursdays', value=51)
    friday = st.sidebar.number_input('Fridays', value=51)
    saturday = st.sidebar.number_input('Saturdays', value=55)
    sunday = st.sidebar.number_input('Sundays', value=55)

    # Add the number of days per year 

    try:
        calendar['days_per_year'] = 0
    except NameError:
        st.error('Please upload a calendar.txt')
        sys.exit(1)
    calendar.loc[calendar['monday']>0, 'days_per_year'] = calendar.loc[calendar['monday']>0, 'days_per_year'] + monday
    calendar.loc[calendar['tuesday']>0, 'days_per_year'] = calendar.loc[calendar['tuesday']>0, 'days_per_year'] + tuesday
    calendar.loc[calendar['wednesday']>0, 'days_per_year'] = calendar.loc[calendar['wednesday']>0, 'days_per_year'] + wednesday
    calendar.loc[calendar['thursday']>0, 'days_per_year'] = calendar.loc[calendar['thursday']>0, 'days_per_year'] + thursday
    calendar.loc[calendar['friday']>0, 'days_per_year'] = calendar.loc[calendar['friday']>0, 'days_per_year']  + friday
    calendar.loc[calendar['saturday']>0, 'days_per_year'] = calendar.loc[calendar['saturday']>0, 'days_per_year'] + saturday
    calendar.loc[calendar['sunday']>0, 'days_per_year'] = calendar.loc[calendar['sunday']>0, 'days_per_year'] + sunday

    calendar['service_days'] = calendar.iloc[:,3:10].sum(axis=1)


    # Define CRS used for calculation based on shapefile
    def code(gdf):
        gdf.index=list(range(0,len(gdf)))
        gdf.crs = {'init':'epsg:4326'}
        lat_referece = gdf.geometry[0].coords[0][1]
        lon_reference = gdf.geometry[0].coords[0][0]

        zone = utm.from_latlon(lat_referece, lon_reference)
        #The EPSG code is 32600+zone for positive latitudes and 32700+zone for negatives.
        if lat_referece <0:
            epsg_code = 32700 + zone[2]
        else:
            epsg_code = 32600 + zone[2]
        
        return epsg_code
    
    try:
        localcrs = code(aux)
    except NameError:
        st.error('Please upload a shapes.txt')
        sys.exit(1)
    
    
    # I need the route_id in stop_times
    try:
        stop_times = pd.merge(stop_times, trips, how='left')
    except NameError:
        st.error('Please upload a stop_times.txt and trips.txt file')
        sys.exit(1)
    
    # I need the route_short_name in trips
    try:
        trips = pd.merge(trips, routes[['route_id', 'route_short_name']])
    except NameError:
        st.error('Please upload a route.txt file')
        sys.exit(1)
    
    #Replace route_id and get rid of route_id in trip_id
    trips['trip_id'] = trips.apply(lambda row: re.sub(r"[\([{})\]]", "", row.trip_id) , axis =1)
    trips['route_id'] = trips.apply(lambda row: re.sub(r"[\([{})\]]", "", row.route_id) , axis =1)
    trips['trip_id'] = trips.apply(lambda row: re.sub(row.route_id,'', row.trip_id), axis =1)

    routes['route_id'] = routes.apply(lambda row: re.sub(r"[\([{})\]]", "", row.route_id) , axis =1)
    stop_times['trip_id'] = stop_times.apply(lambda row: re.sub(r"[\([{})\]]", "", row.trip_id) , axis =1)
    stop_times['route_id'] = stop_times.apply(lambda row: re.sub(r"[\([{})\]]", "", row.route_id) , axis =1)
    stop_times['trip_id'] = stop_times.apply(lambda row: re.sub(row.route_id,'', row.trip_id), axis =1)

    # I need the start and end coordinate in shapes
    def startcoord(row):
        first = Point(row['geometry'].coords[0])
        return first

    def endcoord(row):
        last = Point(row['geometry'].coords[-1])
        return last

    shapes['startcoord'] = shapes.apply(lambda row: startcoord(row), axis=1)
    shapes['endcoord'] = shapes.apply(lambda row: endcoord(row), axis=1)
    
    # Create GDF from points
    try:
        geometry = [Point(xy) for xy in zip(stops.stop_lon, stops.stop_lat)]
    except NameError:
        st.error('Please upload a stops.txt file')
        sys.exit(1)

    stops = stops.drop(['stop_lon', 'stop_lat'], axis=1)
    stops_gdf = GeoDataFrame(stops, crs="EPSG:4326", geometry=geometry)

    # Get polygon by stop
    try:
        stops_poly = gpd.sjoin(stops_gdf,polys,how="left",op="intersects")
    except NameError:
        st.error('Please upload a polygon file named features.geojson')
        sys.exit(1)

    try:
        stop_times = pd.merge(stop_times, stops_poly.loc[:,['stop_id','name']], how='left')
    except KeyError:
        st.error('The geojson file is missing a column called "name"')
        sys.exit(1)

    stop_times['departure_m'] = (stop_times['departure_time'].str.split(':').apply(lambda x:x[0]).astype(int)*60)+(stop_times['departure_time'].str.split(':').apply(lambda x:x[1]).astype(int))+(stop_times['departure_time'].str.split(':').apply(lambda x:x[2]).astype(int)/60)

    # Add service_days to stop_times for ntrips calculation
    stop_times = pd.merge(stop_times, calendar[['service_id','days_per_year']], how='left')

    # Add diff kmh per trip and stop
    stop_times['diff_min'] = np.where(stop_times['stop_sequence'] > 1, stop_times['departure_m'] - stop_times['departure_m'].shift(1), 0)
    stop_times['diff_dist'] = np.where(stop_times['stop_sequence'] > 1, stop_times['shape_dist_traveled'] - stop_times['shape_dist_traveled'].shift(1), 0)

    stop_times['diff_kmh'] = (stop_times.diff_dist/stop_times.diff_min)/(1000/60)
    stop_times = stop_times.replace([np.inf, -np.inf],np.nan)    

    # Get minutes per shape - needed to calculate driven hours in polygon
    min_per_shape = stop_times.groupby(['trip_id','shape_id','name','route_id','service_id','direction_id']).aggregate({'departure_m':lambda x: max(x)-min(x),'shape_dist_traveled':lambda x: max(x)-min(x),'days_per_year':'max','diff_kmh':'mean'}).reset_index()
    #min_per_shape['departure_m'] = min_per_shape.departure_m.apply(lambda x: 0.5 if x == 0 else x) # removed because it reduces the avg km/h

    # Get split location for pattern
    def splitloc(tripid):
        loc = 2
        if tripid.startswith('Service'):
            loc = 3
        return loc 
    loc = splitloc(min_per_shape['trip_id'][1])

    # Split out patternname from trip_id
    min_per_shape['patternname'] = min_per_shape['trip_id'].str.split('-').apply(lambda x:x[loc]) #new

    min_per_shape['poly_kmh'] = (min_per_shape.shape_dist_traveled/min_per_shape.departure_m)/(1000/60)
    min_per_shape1 = min_per_shape.groupby(['shape_id','name','route_id','service_id','direction_id','patternname']).aggregate({'trip_id':'count','days_per_year':'max','departure_m':'sum','poly_kmh':'mean','diff_kmh':'mean'}).reset_index() #update
    min_per_shape1['ntrips'] = min_per_shape1.trip_id * min_per_shape1.days_per_year

    min_per_shape2 = min_per_shape1.groupby(['route_id','shape_id','direction_id','name','patternname']).aggregate({'service_id':lambda x: list(x),'ntrips':'sum','departure_m':'sum','poly_kmh':'mean','diff_kmh':'mean'}).reset_index() #update

    # Calculate fallback speed by polygon
    min_per_shape3 = min_per_shape2.groupby(['name']).aggregate({'poly_kmh':'mean'}).reset_index()
    dict_min_per_shape = min_per_shape3.set_index('name')['poly_kmh'].to_dict()

    # I need the original length per shape
    shapes.crs = {'init':'epsg:4326'}
    shapes['km_in_shape'] = shapes.geometry.to_crs(localcrs).length/1000

    # Calculate intersection between shapes and polygons #changed
    #intersection = gpd.overlay(shapes, polys, how='intersection').reset_index(drop=False)
    #intersection.crs = {'init':'epsg:4326'}

    # I need the intersection and also to keep the shape_id and poly_id or index
    # Get the intersection between each shape and each polygon #changed

    #intersection_geo = [s.intersection(p) for s in shapes.geometry for p in polys.geometry]
    #intersection = gpd.GeoDataFrame(geometry=intersection_geo)
    #intersection.crs = {'init':'epsg:4326'}

    # Get the shape_ids repeated as many times as polygons there are #changed
    #shape_ids = [[s]*len(polys) for s in shapes.shape_id]
        
    # Get the polygon list as many times as shapes there are #changed
    #poly_index = [list(polys.index) for s in shapes.shape_id]
        
    # Add shape_id and polygon index to my intersection gdf #changed
    #intersection['shape_id'] = list(itertools.chain.from_iterable(shape_ids))
    #intersection['poly_index'] = list(itertools.chain.from_iterable(poly_index))
        
    # Keep only the ones that intersected #changed
    #intersection = intersection.loc[~intersection.geometry.is_empty].reset_index()

    # Calculate the length of the intersection in km #changed
    #intersection['km_in_poly'] = intersection.geometry.to_crs(localcrs).length/1000  # changed from 32632 to 3587
    #intersection['miles_in_poly'] = intersection['km_in_poly']*0.621371
    
    # new test to find intersections
    intersection = gpd.overlay(shapes, polys, how='intersection').reset_index(drop=False)
    intersection.crs = {'init':'epsg:4326'}
    intersection['km_in_poly'] = intersection.geometry.to_crs(localcrs).length/1000

    intersection['miles_in_poly'] = intersection['km_in_poly']*0.621371

    # Get the patters with the same criteria as Remix
    # Pattern A is the one with more trips
    # If two patterns have the same number of trips, then the longer

    # Number of trips per shape
    trips['patternname'] =  trips['trip_id'].str.split('-').apply(lambda x:x[loc]) #add patternname per trip
    trips_per_shape0 = trips.pivot_table('trip_id', index=['route_id', 'shape_id','direction_id','service_id','patternname'], aggfunc='count').reset_index() #update
    trips_per_shape0.rename(columns = dict(trip_id = 'ntrips'), inplace=True)
    shapes.crs = {'init':'epsg:4326'} 
    shapes['length_m'] = shapes.geometry.to_crs(epsg=3587).length # Changed from 4326 # CRS.from_epsg() --> deprecation warning

    # Add service_days and days per year to trips_per_shape0 for ntrips calculation
    trips_per_shape = pd.merge(trips_per_shape0, calendar[['service_id','days_per_year','service_days']], how='left')

    trips_per_shape['trips_per_year'] = trips_per_shape['ntrips']*trips_per_shape['days_per_year']
    trips_per_shape['ntrips'] = trips_per_shape['ntrips']*trips_per_shape['service_days']
   
    trips_per_shape = trips_per_shape.groupby(['route_id','shape_id','direction_id','patternname']).aggregate({'service_id':lambda x: list(x),'ntrips':'sum','trips_per_year':'sum'}).reset_index() # added service_id
    #trips_per_shape =  pd.merge(trips_per_shape, shapes[['shape_id','startcoord','endcoord']], how='left') # added start/end coordinates
    trips_per_shape =  pd.merge(trips_per_shape, shapes[['shape_id']], how='left')
    
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
    
    # Old pattern logic
    # Manage directions
    # direction_0 = patterns.loc[patterns.direction_id == 0].reset_index().drop('index', axis=1)
    # direction_1 = patterns.loc[patterns.direction_id == 1].reset_index().drop('index', axis=1)
    
    # # Haversine formula

    # def distancehav(point1, point2):
    #     dLat = math.radians(point2.y) - math.radians(point1.y)
    #     dLon = math.radians(point2.x) - math.radians(point1.x)
    #     a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(math.radians(point1.y)) * math.cos(math.radians(point2.y)) * math.sin(dLon/2) * math.sin(dLon/2)
    #     distance = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    #     distance = distance * 1000
    #     return distance

    # # Assign patterns - 
    # # These are meant to match shapes in opposite directions under the same pattern 
    # # But they are not the final pattern name
    # # 1. whether the start & end locations exactly match (i.e. does the inbound direction end at the start of the outbound direction, and vice versa)
    # # 2. whether the start & end locations are within 400m of each other
    # # 3. the difference in the number of trips on each day of service

    # assigned_patterns = pd.DataFrame()

    # for r in patterns.route_short_name.unique():
    #     t0 = direction_0.loc[direction_0.route_short_name==r]
    #     t1 = direction_1.loc[direction_1.route_short_name==r]
    
    #     if len(t0) >= len(t1):
    #         longer = t0.reset_index()
    #         shorter = t1.reset_index()
    #     else:
    #         longer = t1.reset_index()
    #         shorter = t0.reset_index()
    
    #     ABC = list(ascii_uppercase) + [letter1+letter2 for letter1 in ascii_uppercase for letter2 in ascii_uppercase]

    #     longer['aux_pattern'] = ''
    #     shorter['aux_pattern'] = ''
    
    #     for i in range(len(longer)):
    #         longer.loc[i, 'aux_pattern'] = ABC[i]
    #         nstops = longer.iloc[i]['nstops']
    #         start_longer = longer.iloc[i]['startcoord']
    #         end_longer = longer.iloc[i]['endcoord']
    #         servicedays_longer = longer.iloc[i]['service_id']
    
    #         for j in range(len(shorter)):
    #             start_shorter = shorter.iloc[j]['startcoord']
    #             end_shorter = shorter.iloc[j]['endcoord']
    #             servicedays_shorter = shorter.iloc[j]['service_id']
    #             condition_start = distancehav(start_shorter, end_longer) <= 400
    #             condition_end = distancehav(start_longer, end_shorter) <= 400
    #             some_days_in_common = len([id for id in servicedays_longer if id in servicedays_shorter])>0
    #             condition3 = nstops*0.95 <= shorter.iloc[j]['nstops'] <= nstops*1.05

    #             if condition_start & condition_end & some_days_in_common: # & condition3: 
    #                 shorter.loc[j, 'aux_pattern'] = ABC[i]
    #             elif shorter.loc[j, 'aux_pattern'] == "":
    #                 shorter.loc[j, 'aux_pattern'] = ABC[-i] # to assign a pattern for all unmatched
    #                 break

    #     assigned_patterns = pd.concat([assigned_patterns,longer])
    #     assigned_patterns = pd.concat([assigned_patterns,shorter])
    #     assigned_patterns.drop('index', inplace=True, axis=1)

    #
    # Intersection geometries I need #changed
    intersection1 = pd.merge(intersection, polys[['name']], how='left')
    intersection1 = gpd.GeoDataFrame(data = intersection1.drop(['geometry'], axis=1), geometry = intersection1.geometry)


    # Old pattern logic
    # Get actual number of stops, trips, trips per year and pattern distance
    # assigned_patterns3 = assigned_patterns.groupby(['route_id', 'route_short_name','aux_pattern','direction_id','shape_id']).aggregate({'nstops':'sum','pattern_dist':'sum','ntrips':'sum','trips_per_year':'max',}).reset_index()
    # assigned_patterns = pd.merge(assigned_patterns.loc[:, ~assigned_patterns.columns.isin(['index','nstops','pattern_dist','ntrips','trips_per_year'])],assigned_patterns3,how='left').reset_index().sort_values(['route_short_name'])
    
    # Merge all variables (trips per year and km per year)
    patterns1 = pd.merge(patterns[['route_short_name','route_id','service_id', 'shape_id','patternname', 'ntrips','trips_per_year','nstops','pattern_dist','direction_id']], intersection1, how='right') # Added trips per year #update
    patterns1 = patterns1.dropna(subset=['service_id']) #update

    # Check if shape was split - if not, use km_in_shape instead of km_in_poly

    replace_length = patterns1.groupby(['route_short_name', 'patternname','shape_id'])['ntrips'].count().reset_index()
    replace_length.rename(columns = dict(ntrips = 'split'), inplace=True)
    patterns1 = pd.merge(patterns1, replace_length, how='left',on=['route_short_name', 'patternname','shape_id']) # Added split count

    patterns1['km_in_poly'] = np.where(patterns1['split'] < 2, patterns1['km_in_shape'],patterns1['km_in_poly'])

    #replace poly_kmh with diff_kmh if NaN
    min_per_shape2 = min_per_shape2.dropna(subset=['service_id'])
    min_per_shape2['poly_kmh'] = np.where(np.isnan(min_per_shape2['poly_kmh']), min_per_shape2['diff_kmh'] , min_per_shape2['poly_kmh'])

    min_per_shape2 = min_per_shape2.dropna(subset=['service_id'])
    patterns1.service_id = patterns1.service_id.apply(tuple)
    min_per_shape2.service_id = min_per_shape2.service_id.apply(tuple)
    patterns1 = pd.merge(patterns1, min_per_shape2,on=['route_id','service_id', 'shape_id','name','direction_id','patternname'],how='left') # Added poly_kmh
    patterns1["poly_kmh"] = patterns1.poly_kmh.fillna(patterns1.name.map(dict_min_per_shape)) #fillna with fallback kmh (average per polygon)
    patterns1['poly_m'] = (patterns1.km_in_poly / patterns1.poly_kmh)*60 # calculate minutes per polygon

    # Get km and hours per year 
    patterns1['km_per_year'] = patterns1.km_in_poly * patterns1.trips_per_year     # Add km per year
    patterns1['h_per_year'] = (patterns1.poly_m * patterns1.trips_per_year)/60     # Add hours per year

    patterns2 = patterns1.groupby(['route_short_name', 'patternname']).aggregate({'nstops':'max','ntrips_y':'sum','trips_per_year':'sum','km_in_poly':'sum','km_per_year':'sum','pattern_dist':'max','h_per_year':'sum'}).reset_index().sort_values(by = ['route_short_name','ntrips_y'], ascending=False) # New
    patterns2.reset_index(inplace=True)
    patterns2.drop('index', axis=1, inplace=True)

    # Old pattern logic
    # Assigned patterns depending on the total trips for both directions combined
    # for r in assigned_patterns2.route_short_name.unique():
    #     aux = assigned_patterns2.loc[assigned_patterns2.route_short_name==r]
    #     pattern_list = list(ABC[0:len(aux)])
    #     assigned_patterns2.loc[assigned_patterns2.route_short_name==r, 'pattern'] = pattern_list

    # Merge dataframe with the real patterns and df with the municipalities
    df1 = patterns1[['route_short_name', 'patternname', 'shape_id', 'name', 'trips_per_year','km_in_poly','geometry','km_per_year','h_per_year']] # Added km_per_year and h_per_year
    df2 = patterns2[['route_short_name', 'patternname']]
    
    # This is what I need to show the table
    # I have the fields to filter by route and county
    try_this = pd.merge(df1, df2, how='left')
    table = try_this.pivot_table(['trips_per_year','km_in_poly','km_per_year','h_per_year'], index=['route_short_name', 'patternname', 'name'], aggfunc='sum').reset_index() # Added km_per_year and h_per_year
    table.rename(columns = dict(route_short_name = 'Line', name = 'Area', patternname = 'Pattern',trips_per_year='Fahrten pro Jahr', km_in_poly = 'Kilometer im Gebiet', km_per_year = 'Kilometer im Jahr', h_per_year = 'Stunden im Jahr'), inplace=True)
    
    # Assign color to patterns
    color_lookup = pdk.data_utils.assign_random_colors(try_this['patternname'])
    try_this['color'] = try_this.apply(lambda row: color_lookup.get(row['patternname']), axis=1)

    # This is what I need to draw the map
    # I have the fields to filter by route and county
    gdf_intersections = gpd.GeoDataFrame(data = try_this[['route_short_name', 'name', 'patternname','color']], geometry = try_this.geometry)
    gdf_intersections.rename(columns = dict(route_short_name = 'Line', name = 'Area', patternname = 'Pattern', color = 'Color'), inplace=True)
    
    # -------------------------------------------------------------------------------
    # --------------------------- APP -----------------------------------------------
    # -------------------------------------------------------------------------------
    # LAYING OUT THE TOP SECTION OF THE APP
    st.header("Bus kilometer per Area (geografic boundary)")
    # LAYING OUT THE MIDDLE SECTION OF THE APP WITH THE MAPS
    col1, col2, col3= st.columns((1, 3 ,2)) #NEW
        
    # Select filters
    poly_names_list = list(gdf_intersections['Area'].unique())
    lines_names_list = list(gdf_intersections['Line'].unique())
    lines_names_list = [str(x) for x in lines_names_list]
    patterns_names_list = list(gdf_intersections['Pattern'].unique())
    patterns_names_list = [str(x) for x in patterns_names_list]


    poly_names_list.sort()
    lines_names_list.sort()
    patterns_names_list.sort()
    
    with col1:
        st.subheader('Filter')
        filter_polys = st.multiselect('Area', poly_names_list)
        filter_routes = st.multiselect('Line', lines_names_list)
        filter_patterns = st.multiselect('Pattern', patterns_names_list)
        st.subheader('Pivot Dimensionen')
        group_by = st.multiselect('Group by', ['Area', 'Line', 'Pattern'], default = ['Area', 'Line', 'Pattern'])
        
    if filter_polys == []:
        filter_polys = poly_names_list
        
    if filter_routes == []:
        filter_routes = lines_names_list

    if filter_patterns == []:
        filter_patterns = patterns_names_list

    # Work for the datatable
    # Aggregate data as indicated in Pivot dimensions    
    # Filter data
    table_poly = table.loc[
        (table['Line'].isin(filter_routes))&
        (table['Area'].isin(filter_polys))&
        (table['Pattern'].isin(filter_patterns))
        ]
    #table_poly = table_poly.pivot_table(['Fahrten pro Jahr','Kilometer im Gebiet','Kilometer im Jahr','Stunden im Jahr'], index=group_by, aggfunc='sum').reset_index() # Added km_per_year
    table_poly = table_poly.pivot_table(['Fahrten pro Jahr','Kilometer im Gebiet','Kilometer im Jahr','Stunden im Jahr'], index=group_by, aggfunc={'Fahrten pro Jahr': "sum", 'Kilometer im Gebiet': "sum",'Kilometer im Jahr':"sum",'Stunden im Jahr': "sum"}).reset_index() 
    table_poly['Fahrten pro Jahr'] = table_poly['Fahrten pro Jahr'].apply(lambda x: str(round(x, 2)))     
    table_poly['Kilometer im Gebiet'] = table_poly['Kilometer im Gebiet'].apply(lambda x: str(round(x, 2)))     
    table_poly['Kilometer im Jahr'] = table_poly['Kilometer im Jahr'].apply(lambda x: str(round(x, 2)))     
    table_poly['Stunden im Jahr'] = table_poly['Stunden im Jahr'].apply(lambda x: str(round(x, 2)))     

                
    # Filter polygons that passed the filter
    # Merge the intersection with the number of trips per shape
    intersection_aux = pd.merge(trips, intersection1, how='right')
    intersection2 = intersection_aux.drop_duplicates(subset=['route_short_name', 'name']).loc[:,['route_short_name', 'name']].reset_index()
    
    # Add polygons geometries
    intersection2 = pd.merge(intersection2, polys, left_on='name', right_on='name', how='left')
    
    # This is what I need to select the polygons that passed the route and county filters
    route_polys = gpd.GeoDataFrame(data=intersection2[['route_short_name', 'name']], geometry=intersection2.geometry)
    
    filtered = route_polys.loc[
        (route_polys['name'].isin(filter_polys))&
        (route_polys.route_short_name.isin(filter_routes))
        ]
        
    # Filter line intersections that passed the filters
    line_intersections = gdf_intersections.loc[
        (gdf_intersections['Line'].isin(filter_routes))&
        (gdf_intersections['Area'].isin(filter_polys))&
        (gdf_intersections['Pattern'].isin(filter_patterns))
        ].__geo_interface__
    
    # Filter the shapes that passed the routes filters
    aux = trips.drop_duplicates(subset=['route_id', 'shape_id'])
    aux = pd.merge(aux, routes[['route_id', 'route_short_name']], how='left')
    shapes_filtered = pd.merge(shapes ,aux, how='left')
    shapes_filtered = pd.merge(shapes_filtered, try_this[['shape_id','route_short_name','color', 'patternname']], how='left')
    shapes_filtered = gpd.GeoDataFrame(data = shapes_filtered.drop('geometry', axis=1), geometry=shapes_filtered.geometry)
    shapes_filtered = shapes_filtered.loc[shapes_filtered.route_short_name.isin(filter_routes)]
    
    # Calculate the center
    avg_lon = polys.geometry.centroid.x.mean()
    avg_lat = polys.geometry.centroid.y.mean()    

    with col2:
        st.subheader('Total Kilometer per area = {}'.format(round(table_poly['Kilometer im Gebiet'].map(float).sum(),1)))
                    # Download data

        def get_table_download_link(df):
            """Generates a link allowing the data in a given panda dataframe to be downloaded
            in:  dataframe
            out: href string
            """
            csv = df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()  # some strings <-> bytes conversions necessary here
            href = f'<a href="data:file/csv;base64,{b64}">Export CSV file</a>'
            return href
        
        gb = GridOptionsBuilder.from_dataframe(table_poly) #NEW

        gb.configure_default_column(
            resizable=True,
            filterable=True,
            sortable=True,
            editable=False,
            )#NEW
        
        gb.configure_column( 
            field="Line", 
            header_name="Line", 
            pinned='left',
        ) #NEW

        gb.configure_column(
            field="Fahrten pro Jahr",
            header_name="Trips/year",
            width=100,
            tooltipField="Trips per year",
        ) #NEW

        gb.configure_column(
            field="Kilometer im Gebiet",
            header_name="Km/Area",
            width=100,
            tooltipField="Kilometer per Area",
            type=["numericColumn"],
        ) #NEW

        gb.configure_column(
            field="Kilometer im Jahr",
            header_name="Km/year",
            width=100,
            tooltipField="Kilometer per year",
            type=["numericColumn"],
        ) #NEW

        gb.configure_column(
            field="Stunden im Jahr",
            header_name="h/year",
            width=100,
            tooltipField="Hours per year",
            type=["numericColumn"],
        ) #NEW
        
        #gb.configure_side_bar() #NEW
        gb.configure_grid_options(
            tooltipShowDelay=0
            )#NEW

        go = gb.build() #NEW

        AgGrid(table_poly, gridOptions=go, theme="streamlit") #NEW
        #st.dataframe(table_poly, 1200, 600) #NEW
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
                    #get_line_color = shapes_filtered['color'],
                    #get_fill_color=shapes_filtered['color'],
                    #get_fill_color=[231,51,55],
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
                    #get_line_color = [200,51,55],
                    get_line_color = "properties.Color",
                    #get_fill_color=line_intersections['Color'],
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
        
