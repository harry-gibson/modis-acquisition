#-------------------------------------------------------------------------------
# Name:     calculate_temps
# Purpose:  Calculate Land Surface Temperature (day and night) in celsius from a MOD11A2 image
# Note:     This is a simple modification of gdal_calc.py to process native (hardcoded) 
#           blocksizes of HDF files, for more efficient I/O, and using numexpr for calculation
#           As such there's various redundant code in main and elsewhere
#-----------------------------------------------------

from osgeo import gdal
import numpy as np
import os
import sys
from optparse import OptionParser
import numexpr as ne

RequiredBandList = ["DayInput","NightInput"]

# set up some default nodatavalues for each datatype
DefaultNDVLookup={'Byte':255, 'UInt16':65535, 'Int16':-32767, 'UInt32':4294967293, 'Int32':-2147483647, 'Float32':1.175494351E-38, 'Float64':1.7976931348623158E+308}
OutputNDV = 0
gdalDatasetsIn = []

# scale conversion
_MODIS_SCALE_CONST = 0.02
_MODIS_OFFSET_CONST = -273.15

################################################################
# set up output files
################################################################

def setupOutput(outputFN, opts, XSize, YSize, fileType=None, ndv=None):

    global gdalDatasetsIn, OutputNDV
    # open output file exists
    if os.path.isfile(outputFN) and not opts.overwrite:
        if opts.debug:
            print("Output file %s exists - filling in results into file" %(outputFN))
        myOut=gdal.Open(outputFN, gdal.GA_Update)
        if [myOut.RasterXSize,myOut.RasterYSize] != [XSize, YSize]:
            print("Error! Output exists, but is the wrong size.  Use the --overwrite option to automatically overwrite the existing file")
            return
        myOutB=myOut.GetRasterBand(1)
        OutputNDV=myOutB.GetNoDataValue()
        myOutType=gdal.GetDataTypeName(myOutB.DataType)

    else:
        # remove existing file and regenerate
        if os.path.isfile(outputFN):
            os.remove(outputFN)
        # create a new file
        if opts.debug:
            print("Generating output file %s" %(outputFN))

        # find data type to use
        if not fileType:
            # use the largest type of the input files
            myOutType=gdal.GetDataTypeName(max(myDataTypeNum))
        else:
            myOutType=fileType

        # create file
        myOutDrv = gdal.GetDriverByName(opts.format)
        myOut = myOutDrv.Create(
            outputFN, XSize, YSize, 1,
            gdal.GetDataTypeByName(myOutType), opts.creation_options)

        # set output geo info based on first input layer
        myOut.SetGeoTransform(gdalDatasetsIn[0].GetGeoTransform())
        myOut.SetProjection(gdalDatasetsIn[0].GetProjection())

        if ndv!=None:
            OutputNDV=ndv
        else:
            OutputNDV=DefaultNDVLookup[myOutType]

        myOutB = myOut.GetRasterBand(1)
        myOutB.SetNoDataValue(OutputNDV)
        myOutB = None

    #if opts.debug:
    #    print("output file: %s, dimensions: %s, %s, type: %s" %(outputFN,myOut.RasterXSize,myOut.RasterYSize,gdal.GetDataTypeName(myOutB.DataType)))
    return myOut


def doit(opts, args):
    global gdalDatasetsIn
    #bandsIn = []
    dataTypes = []
    dataTypeNums = []
    inputNDVs = np.empty(len(RequiredBandList))

    DimensionsCheck = None
    # check dimensions of inputs
    # loop through input files - checking dimensions
    for i,myI in enumerate(RequiredBandList[0:len(sys.argv)-1]):
        thisFN = eval("opts.%s" %(myI))
        #myBand = eval("opts.%s_band" %(myI))
        if thisFN:
            gdalDatasetsIn.append(gdal.Open(thisFN, gdal.GA_ReadOnly))
            dataTypes.append(gdal.GetDataTypeName(gdalDatasetsIn[i].GetRasterBand(1).DataType))
            dataTypeNums.append(gdalDatasetsIn[i].GetRasterBand(1).DataType)
            #inputNDVs.append(gdalDatasetsIn[i].GetRasterBand(1).GetNoDataValue())
            inputNDVs[i] = gdalDatasetsIn[i].GetRasterBand(1).GetNoDataValue()
            # check that the dimensions of each layer are the same
            if DimensionsCheck:
                if DimensionsCheck!=[gdalDatasetsIn[i].RasterXSize, gdalDatasetsIn[i].RasterYSize]:
                    print("Error! Dimensions of file %s (%i, %i) are different from other files (%i, %i).  Cannot proceed" % \
                            (thisFN,gdalDatasetsIn[i].RasterXSize, gdalDatasetsIn[i].RasterYSize,DimensionsCheck[0],DimensionsCheck[1]))
                    return
            else:
                DimensionsCheck=[gdalDatasetsIn[i].RasterXSize, gdalDatasetsIn[i].RasterYSize]
            if opts.debug:
                print("file %s: %s, dimensions: %s, %s, type: %s" %(myI,thisFN,DimensionsCheck[0],DimensionsCheck[1],dataTypes[i]))


    # set up output files
    dayTempOut = setupOutput(opts.dayOutputFN, opts, DimensionsCheck[0], DimensionsCheck[1], 'Float32', opts.NoDataValue)
    nightTempOut = setupOutput(opts.nightOutputFN, opts, DimensionsCheck[0], DimensionsCheck[1], 'Float32', opts.NoDataValue)
    
    #myBlockSize = gdalDatasetsIn[0].GetRasterBand(1).GetBlockSize()
    # vrt file reports a block size of 128*128 but the underlying hdf block size is 1200*100
    # so hard code this, or some clean multiple : this minimises disk access
    myBlockSize = [4800,4800]
    nXValid = myBlockSize[0]
    nYValid = myBlockSize[1]
    nXBlocks = (int)((DimensionsCheck[0] + myBlockSize[0] - 1) / myBlockSize[0]);
    nYBlocks = (int)((DimensionsCheck[1] + myBlockSize[1] - 1) / myBlockSize[1]);
    myBufSize = myBlockSize[0]*myBlockSize[1]

    if opts.debug:
        print("using blocksize %s x %s" %(myBlockSize[0], myBlockSize[1]))

    # variables for displaying progress
    ProgressCt = -1
    ProgressMk = -1
    ProgressEnd = nXBlocks * nYBlocks * 1 # for allBandsCount, removed


    ################################################################
    # start looping through blocks of data
    ################################################################

    # loop through X-lines
    for X in range(0,nXBlocks):

        # in the rare (impossible?) case that the blocks don't fit perfectly
        # change the block size of the final piece
        if X==nXBlocks-1:
            nXValid = DimensionsCheck[0] - X * myBlockSize[0]
            myBufSize = nXValid*nYValid

        # find X offset
        myX=X*myBlockSize[0]

        # reset buffer size for start of Y loop
        nYValid = myBlockSize[1]
        myBufSize = nXValid * nYValid

        # loop through Y lines
        for Y in range(0,nYBlocks):
            ProgressCt+=1
            if 10*ProgressCt/ProgressEnd%10!=ProgressMk:
                ProgressMk=10*ProgressCt/ProgressEnd%10
                from sys import version_info
                if version_info >= (3,0,0):
                    exec('print("%d.." % (10*ProgressMk), end=" ")')
                else:
                    exec('print 10*ProgressMk, "..",')

           #print ".",
            # change the block size of the final piece
            if Y==nYBlocks-1:
                nYValid = DimensionsCheck[1] - Y * myBlockSize[1]
                myBufSize = nXValid*nYValid

            # find Y offset
            myY=Y*myBlockSize[1]

            # create empty buffer to mark where nodata occurs
            myNDVs=np.zeros(myBufSize*len(gdalDatasetsIn))
            myNDVs.shape=(len(gdalDatasetsIn),nYValid,nXValid)

            # fetch data for each input layer
            bands = np.empty(shape=(2, nYValid,nXValid),
                                 dtype=gdal.GetDataTypeName(max(dataTypeNums)))
            for i,OptName in enumerate(RequiredBandList):

                # populate lettered arrays with values
                #if allBandsIndex is not None and allBandsIndex==i:
                #    myBandNo=bandNo
                #else:
                #    myBandNo=myBands[i]
                myBandNo = 1
                bands[i]=gdalDatasetsIn[i].GetRasterBand(myBandNo).ReadAsArray(
                                      xoff=myX, yoff=myY,
                                      win_xsize=nXValid, win_ysize=nYValid)

                # create an array of values for this block
                exec("%s=bands[i]" %OptName)

                #myval=None
            # fill in nodata values
            #myNDVs=1*np.logical_or(myNDVs==1, bands[i]==myNDV[i])
            myNDVs = bands == inputNDVs[:,np.newaxis,np.newaxis]
            
            # try the calculation on the array blocks
            try:
                # Do it with numexpr for easy multithreading:
                #dayResult = ne.evaluate("(DayInput * _MODIS_SCALE_CONST) + _MODIS_OFFSET_CONST")
                #nightResult = ne.evaluate("(DayInput * _MODIS_SCALE_CONST)  + _MODIS_OFFSET_CONST")
                result = ne.evaluate("(bands * _MODIS_SCALE_CONST) + _MODIS_OFFSET_CONST")
            except:
                #print("evaluation of calculation %s failed" %(opts.calc))
                raise

            # propogate nodata values
            # (set nodata cells to zero then add nodata value to these cells)

            if 1: #useNumExpr:
                result = ne.evaluate("((1 * (myNDVs==0))*result) + (OutputNDV * myNDVs)")
                
            else:
                result = ((1 * (myNDVs==0))*result) + (OutputNDV * myNDVs)

            # write data block to the output file
            dayOutB=dayTempOut.GetRasterBand(1)
            nightOutB=nightTempOut.GetRasterBand(1)
            # this order relies on "day" being enumerated before "night"!
            dayOutB.WriteArray(result[0], xoff=myX, yoff=myY)
            nightOutB.WriteArray(result[1], xoff=myX, yoff=myY)
    print ("100 - Done")
    return

def main():
    usage = "usage: %prog [--B1 <filename>] ... [--B7 <filename>] [--EVIFile <filename>] [--TCBFile <filename>] [--TCWFile <filename>]"
    parser = OptionParser(usage)


    parser.add_option("--DayInput", dest="DayInput", help="mosaiced band LST Day file (vrt)")
    parser.add_option("--NightInput", dest="NightInput", help="mosaiced LST Night file (vrt)")
    
    parser.add_option("--DayFile", dest="dayOutputFN", help="output Day file to generate or fill")
    parser.add_option("--NightFile", dest="nightOutputFN", help="output Night file to generate or fill")
    
    parser.add_option("--NoDataValue", dest="NoDataValue", type=float, help="set output nodata value (Defaults to datatype specific value)")
    parser.add_option("--type", dest="type", help="output datatype, must be one of %s" % list(DefaultNDVLookup.keys()))
    parser.add_option("--format", dest="format", default="GTiff", help="GDAL format for output file (default 'GTiff')")
    parser.add_option(
        "--creation-option", "--co", dest="creation_options", default=[], action="append",
        help="Passes a creation option to the output format driver. Multiple "
        "options may be listed. See format specific documentation for legal "
        "creation options for each format.")
    parser.add_option("--overwrite", dest="overwrite", action="store_true", help="overwrite output file if it already exists")
    parser.add_option("--debug", dest="debug", action="store_true", help="print debugging information")

    (opts, args) = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
    elif not (opts.DayInput and opts.NightInput and opts.dayOutputFN and opts.nightOutputFN):
        print("Required parameter missing!")
        parser.print_help()
    else:
        doit(opts, args)
    sys.exit(0)

if __name__ == '__main__':
    main()

