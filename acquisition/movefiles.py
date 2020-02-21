#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:		basic script to sort modis tiles from a single directory into subdirectories for each tile reference containing all dates of a given tile.
#
# Author:      zool1301
#
# Created:     23/09/2014
# Copyright:   (c) zool1301 2014
# Licence:     <your licence>
#-------------------------------------------------------------------------------
import os
import collections
import shutil
import csv
import glob
import datetime

reqTiles = None

def parsepath(hdffilepath):
    filename = os.path.split(hdffilepath)[1]
    product,datebit,tile,version,stuff,ext = filename.split('.')
    yrbit = int(datebit[1:5])
    daybit = int(datebit[5:])
    d = datetime.date(yrbit,1,1) + datetime.timedelta(daybit-1)
    dirname = str(d.year)+"_"+str(d.month).zfill(2)
    tileH = tile[1:3]
    tileV = tile[4:]
    return {"Product":product,"Date":d,"TileName":tile,"Yr":yrbit,"Day":daybit,"TileH":tileH,"TileV":tileV,"Version":version,"Type":ext}

def readreqtiles(csvpath):
    with open(csvpath,'rb') as f:
        c = csv.reader(f)
        fn = c.next()
        c = csv.DictReader(f,fn)
        dct = collections.defaultdict(list)
        for i in c:
            dct[str(i['h']).zfill(2)].append(str(i['v']).zfill(2))
        global reqTiles
        reqTiles = dct

def main():
    readreqtiles(r"\\zoo-booty\home$\zool1301\My Documents\MODIS_Processing\modisdownload\modis_tiles_africa.csv")
    # assume they are already downloaded else call a downloader function here
    datadir = r"C:\Users\zool1301\Downloads"
    #outdir = r"C:\Users\zool1301\Documents\MODIS\MOD11A2_2013_Global"
    outdir = r"C:\Users\zool1301\Documents\MODIS\MOD11A2_Global_Day065"
    products = ['MCD43B4','MOD11A2']
    for product in products:
        productindir = os.path.join(datadir,product+"_SingleDay")
        productoutdir = os.path.join(outdir,product)
        productfiles = glob.glob(os.path.join(productindir,"*.hdf"))
        for daytilefile in productfiles:
            filepath = os.path.join(productindir,daytilefile)
            info = parsepath(filepath)
            if not info["Product"] == product:
                continue
            #if not reqTiles[info["TileH"]].count(info["TileV"]) == 0:
            #if 1:
            if info["Day"] == 65:
                outdirtile = os.path.join(productoutdir,info["TileName"])
                if not os.path.isdir(outdirtile):
                    os.makedirs(outdirtile)
                # get the hdf and xml file names if they both exist
                tilefiles = glob.glob(filepath+"*")
                for fn in tilefiles:
                    if 1:
                    #if info["Yr"] != 2013:
                        shutil.move(fn,outdirtile)
                    else:
                        shutil.copy(fn,outdirtile)

if __name__ == '__main__':
    main()