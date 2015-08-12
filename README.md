This repository contains scripts used to go from the NASA MODIS DAAC website (loads of HDF files in a big box in America) to WGS84 global geotiffs of LST, EVI, TCB, and TCW data. 

The basic process is:

- Download tiles using modified get_modis python script - this downloads a whole year / product in one go. Call for multiple years simultaneously using a command prompt for loop. OR use FME workbench if available, or other web scraping tool of choice. 

- Save to a single directory (no need to split by tile or date). This is approx 1Tb in >250000 HDF files for MCD43B4. Around 700Gb for MOD11A2.

- Example: for %y in (2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2014) do (start /b python c:\users\zool1301\downloads\get_modis-1.3.0\get_modis.py -s MOTA -p MCD43B4.005 -y %y -b 001 -e 366)

- This took around 24 hours to download all MCD43B4, running all years simultaneously. Way faster than doing one after another.
- MODIS repository often goes down for maintenance on Wednesdays, so ideally start on a Thursday.
- The script does a cursory check to see if the file exists locally and has same size. So, check the command output to see if any errors occurred (e.g. timeouts) and just rerun on same directory to retry; this takes a considerable time as it has to get the metadata for each remote file to check sizes.

Transform tiles into compressed WGS84 mosaiced tiffs. A batch file, which calls a python script for the calculations, has been provided to do this via temp files on a RAMdisk and local C: disk, using VRT files (Process_MCD43B4_Indices_From_HDF.bat and Process_MOD11A2_Temp_From_HDF.bat)

- It took around 30 hrs to generate all EVI, TCB, and TCW tiffs, and ~20hrs to generate all LST Day and Night tiffs.
- EVI + TCB + TCW total around 900Gb compressed
- LST day + night total around 450Gb compressed
- Stored in Float32 format, not considered worth using Float64. If storage is an issue the LST day and night could be maintained in unscaled Int16 format.
- Projection specification is more precise than old MAP mastergrid template so does not line up precisely. Can be easily swapped without need for reprojection as difference is less than half a cell.

HDF files can now be removed / transferred to a cupboard

Generate mean and standard deviation for each set of tiffs. IPython Notebook CalcMeanAndSD.ipynb provides code to do this using cython for the looping. It calculate outputs for each month and overall.

- Takes ~10hrs for each set of data
- The vast majority of this time (at least 90%) is taken by actually reading the TIFFs in. Uncompressed format would be better speedwise but impractical
- It's essentially impossible to keep a 12 core CPU occupied unless we're doing much more complicated maths than is required here! As it is it can plough through as much data as can fit into 64Gb RAM in just a couple of seconds whereas it takes a substantial time simply to read that from even the fastest disk. Hence I have not really investigated the processing blade servers.

These synoptic mean outputs may be all that some people require. Otherwise run gap fill.

