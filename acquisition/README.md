The get_modis package was acquired from the url given in the python script and the script was trivially modified to grab all tiles (and thus only require a year as input and not a tile). This allows downloading all global tiles for one product and one year in a single command.

It can be run for all years sequentially using the command syntax given in GRAB_all_modis.txt, to grab all tiles for a product ever.

It can be run for multiple years in parallel to take advantage of faster connections. the grab_all_modis_multiprocess.bat was one attempt at this but did not work properly. Instead use the ppx2 tool (or xargs, on linux) to launch multiple versions in parallel.