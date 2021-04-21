# -*- coding: utf-8 -*-
"""
Created on Tue Apr 20 09:13:18 2021

@author: santi
"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
from shapely.geometry import LineString
import itertools
import base64

st.set_page_config(layout="wide")
st.sidebar.header('Upload files and close the sidebar')
uploaded_files = st.sidebar.file_uploader('File uploader', accept_multiple_files=True, type=['txt'])

# Get the polygons
polys = gpd.read_file("https://raw.githubusercontent.com/Bondify/km_per_polygon/main/data/polygons.geojson")
polys = polys.to_crs(epsg=4326)

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
        elif name == 'shapes.txt':
            aux = pd.read_csv(file)
            aux.sort_values(by=['shape_id', 'shape_pt_sequence'], ascending=True, inplace=True)
            aux = gpd.GeoDataFrame(data=aux[['shape_id']], geometry = gpd.points_from_xy(x = aux.shape_pt_lon, y=aux.shape_pt_lat))
            lines = [LineString(list(aux.loc[aux.shape_id==s, 'geometry']))  for s in aux.shape_id.unique()]
            shapes = gpd.GeoDataFrame(data=aux.shape_id.unique(), geometry = lines, columns = ['shape_id'])
    
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
    intersection['km_in_poly'] = intersection.geometry.to_crs(32632).length/1000
    intersection['miles_in_poly'] = intersection['km_in_poly']*0.621371
    
    # Trips per shape and service_id
    trips = pd.merge(trips, routes[['route_id', 'route_short_name']])
    
    trips_per_shape = trips.pivot_table('trip_id', index=['route_short_name','shape_id', 'service_id'], aggfunc='count').reset_index()
    trips_per_shape.rename(columns=dict(trip_id='ntrips'), inplace=True)
    
    # Merge the intersection with the number of trips per shape
    intersection1 = pd.merge(trips_per_shape, intersection, how='right')
    intersection1['total_km'] = intersection1['ntrips']*intersection1['km_in_poly']
    intersection1['total_miles'] = intersection1['ntrips']*intersection1['miles_in_poly']
    
    intersection1 = gpd.GeoDataFrame(data = intersection1.drop('geometry', axis=1), geometry = intersection1.geometry)
    
    # Aggregate at the route level (we don't really care about the shape_id)
    # The big downside with this is that we lose the geometry
    intersection2 = intersection1.pivot_table(
        ['total_km', 'km_in_poly','total_miles', 'miles_in_poly','ntrips'],
        index = ['route_short_name', 'service_id', 'poly_index'],
        aggfunc='sum'
    ).reset_index()    
            
    intersection2 = pd.merge(intersection2, polys, left_on='poly_index', right_on=polys.index, how='left')
    intersection2.rename(columns = dict(
        route_short_name = 'Route',
        service_id = 'Service ID',
        NAME = 'County'
        ), inplace=True)
    
    intersection3 = gpd.GeoDataFrame(data=intersection2.drop('geometry', axis=1), geometry=intersection2.geometry)

    # -------------------------------------------------------------------------------
    # --------------------------- APP -----------------------------------------------
    # -------------------------------------------------------------------------------
    # LAYING OUT THE TOP SECTION OF THE APP
    st.header("Bus kilometers per county")
    # LAYING OUT THE MIDDLE SECTION OF THE APP WITH THE MAPS
    col1, col2, col3= st.beta_columns((1, 2 ,3))
        
    # Select filters
    poly_names_list = list(intersection3['County'].unique())
    lines_names_list = list(intersection3['Route'].unique())
    
    poly_names_list.sort()
    lines_names_list.sort()
    
    with col1:
        st.subheader('Filters')
        filter_polys = st.multiselect('Counties', poly_names_list)
        filter_routes = st.multiselect('Routes', lines_names_list)
        st.subheader('Pivot dimensions')
        group_by = st.multiselect('Group by', ['County', 'Route', 'Service ID'], default = ['County', 'Route'])
        
    if filter_polys == []:
        filter_polys = list(intersection3['County'].unique())
        
    if filter_routes == []:
        filter_routes = list(intersection3['Route'].unique())
        
        
    # # Get the total_km per polygon for map styling
    # total_km_per_poly = intersection3.loc[intersection3.route_short_name.isin(filter_routes)].pivot_table(['total_km','total_miles'], index=['NAME'], aggfunc='sum').reset_index()
    # total_km_per_poly = pd.merge(total_km_per_poly, polys[['NAME', 'geometry']], how='left')
    # total_km_per_poly = gpd.GeoDataFrame(data=total_km_per_poly.drop('geometry', axis=1), geometry=total_km_per_poly.geometry)
    
    # # Calculate weigth for styling
    # total_km_per_poly['weight'] = total_km_per_poly.total_km/total_km_per_poly.total_km.max()
    
    # # Filter the polygons that pass the filter for the map
    # filtered = total_km_per_poly.loc[total_km_per_poly['NAME'].isin(filter_polys)]
    # # Data for map
    # data_poly = filtered.__geo_interface__
        
    # # Calculate the center of the filter polygons
    # avg_lon = total_km_per_poly.loc[total_km_per_poly['NAME'].isin(filter_polys), 'geometry'].centroid.x.mean()
    # avg_lat = total_km_per_poly.loc[total_km_per_poly['NAME'].isin(filter_polys), 'geometry'].centroid.y.mean()
        
    # Filter polygons that passed the filter
    filtered = intersection3.loc[
        (intersection3['County'].isin(filter_polys))&
        (intersection3.Route.isin(filter_routes))
        ]
    
    # Filter line intersections that passed the filters
    line_intersections = intersection1.loc[
        (intersection1.route_short_name.isin(filter_routes))&
        (intersection1.poly_index.isin(polys.loc[polys['NAME'].isin(filter_polys)].index.unique()))
        ].__geo_interface__
    
    # Filter the shapes that passed the routes filters
    aux = trips.drop_duplicates(subset=['route_id', 'shape_id'])
    aux = pd.merge(aux, routes[['route_id', 'route_short_name']], how='left')
    shapes_filtered = pd.merge(shapes ,aux, how='left')
    shapes_filtered = gpd.GeoDataFrame(data = shapes_filtered.drop('geometry', axis=1), geometry=shapes_filtered.geometry)
    shapes_filtered = shapes_filtered.loc[shapes_filtered.route_short_name.isin(filter_routes)]
    
    # Calculate the center
    avg_lon = polys.geometry.centroid.x.mean()
    avg_lat = polys.geometry.centroid.y.mean()
    
    # Work for the datatable
    # Aggregate data as indicated in Pivot dimensions    
    # Filter data
    table_poly = filtered.pivot_table(['total_km'], index=group_by, aggfunc='sum').reset_index()
    table_poly['total_km'] = table_poly['total_km'].apply(lambda x: str(round(x, 2)))         

    with col2:
        st.subheader('Total km = {}'.format(round(filtered.total_km.sum(),1)))
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
                    opacity=0.2,
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
                    # get_fill_color=[231,51,55],
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
        
