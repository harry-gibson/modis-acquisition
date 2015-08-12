#-------------------------------------------------------------------------------
# Name:     calculate_indices
# Purpose:  Calculate vegetation indices (EVI, TCB, TCW) for a 7-band MCD43B4 image
# Note:     This is a simple modification of gdal_calc.py to process native (hardcoded) 
#           blocksizes of HDF files, for more efficient I/O, and using numexpr for calculation
#           As such there's various redundant code in main and elsewhere
#-------------------------------------------------------------------------------

from osgeo import gdal
import numpy as np
import os
import sys
from optparse import OptionParser
import numexpr as ne

RequiredBandList = ["B1","B2","B3","B4","B5","B6","B7"]

# set up some default nodatavalues for each datatype
DefaultNDVLookup={'Byte':255, 'UInt16':65535, 'Int16':-32767, 'UInt32':4294967293, 'Int32':-2147483647, 'Float32':1.175494351E-38, 'Float64':1.7976931348623158E+308}
OutputNDV = 0
gdalDatasetsIn = []

#define (hard code) the index calculations
#eviCalc = "(((B - A) / (B + (A * 6.0) - (C * 7.5) +1.0) * 2.5))"
#tcbCalc = "((A * 0.4395) + (B * 0.5945)+ (C * 0.2460)+ (D * 0.3918)+ (E * 0.3506)+ (F * 0.2136)+ (G * 0.2678)) * 0.0001"
#tcwCalc = "((A * 0.1147) + (B * 0.2489)+ (C * 0.2408)+ (D * 0.3132)+ (E * -0.3132)+ (F * -0.6416)+ (G * -0.5087)) * 0.0001"


# EVI coefficients from huete et al
_EVI_C1 = 6.0
_EVI_C2 = 7.5
_EVI_L = 1.0 #muhahaha
_EVI_G = 2.5

# tasseled cap coefficients provided by Dan Weiss
# tasseled cap brightness coefficients
_TCB_COEFFS = np.asarray(
    [0.4395, 0.5945, 0.2460, 0.3918, 0.3506, 0.2136, 0.2678]
    ).reshape(7,1,1)

# tasseled cap wetness coefficients
_TCW_COEFFS = np.asarray(
    [0.1147, 0.2489, 0.2408, 0.3132, -0.3122, -0.6416, -0.5087]
    ).reshape(7,1,1)

# scale conversion
_MODIS_SCALE_CONST = 0.0001


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
    eviOut = setupOutput(opts.eviOutputFN, opts, DimensionsCheck[0], DimensionsCheck[1], 'Float32', opts.NoDataValue)
    tcwOut = setupOutput(opts.tcwOutputFN, opts, DimensionsCheck[0], DimensionsCheck[1], 'Float32', opts.NoDataValue)
    tcbOut = setupOutput(opts.tcbOutputFN, opts, DimensionsCheck[0], DimensionsCheck[1], 'Float32', opts.NoDataValue)

    #myBlockSize = gdalDatasetsIn[0].GetRasterBand(1).GetBlockSize()
    # vrt file reports a block size of 128*128 but the underlying hdf block size is 1200*100
    # so hard code this, or some clean multiple : using 2400 * 2400 here which is the size
    # of the file itself. this minimises disk access
    myBlockSize = [2400,2400]
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
            bands = np.empty(shape=(7, nYValid,nXValid),
                                 dtype=gdal.GetDataTypeName(max(dataTypeNums)))
            for i,Alpha in enumerate(RequiredBandList):

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
                TCBAlpha = "TCB"+str(i)
                TCWAlpha = "TCW"+str(i)
                exec("%s=_TCW_COEFFS[i]" %TCWAlpha)
                exec("%s=_TCB_COEFFS[i]" %TCBAlpha)
                exec("%s=bands[i]" %Alpha)

                #myval=None
            # fill in nodata values
            #myNDVs=1*np.logical_or(myNDVs==1, bands[i]==myNDV[i])
            myNDVs = bands == inputNDVs[:,np.newaxis,np.newaxis]
            
            # possibly do a rgb image too? http://www.idlcoyote.com/ip_tips/brightmodis.html and
            # http://www.idlcoyote.com/programs/scalemodis.pro
            # but scaling method would only work if we know the whole image's stats
            #rgbInOut = [[0,0],[30,110],[60,160],[120,210],[190,240],[255,255]]
            #rgbInOutRange = [-0.01, 1.10]

            # try the calculation on the array blocks
            try:
                
                # evi from equation 12 in Huete et al
                # Do it with numexpr for easy multithreading:
                #eviResult = ne.evaluate("(((B2 - B1) / (B2 + (B1 * _EVI_C1) - (B3 * _EVI_C2) + _EVI_L) * _EVI_G))")
                eviResult = ne.evaluate("((((B2 - B1)*_MODIS_SCALE_CONST) / ((B2 + (B1 * _EVI_C1) - (B3 * _EVI_C2))*_MODIS_SCALE_CONST + _EVI_L) * _EVI_G))")

                tcbResult = ne.evaluate ("(B1*TCB0 + B2*TCB1 + B3*TCB2 + B4*TCB3 + B5*TCB4 + B6*TCB5 + B7*TCB6)*_MODIS_SCALE_CONST")
                tcwResult = ne.evaluate("(B1*TCW0 + B2*TCW1 + B3*TCW2 + B4*TCW3 + B5*TCW4 + B6*TCW5 + B7*TCW6)*_MODIS_SCALE_CONST")
                np.clip(eviResult,0,1,out=eviResult)
                np.clip(tcbResult,-100,100,out=tcbResult)
                np.clip(tcwResult,-100,100,out=tcwResult)
                # todo : handle nan in evi? i.e. when it is divide by zero
                
                # or classic numpy version:
                #eviResult = (((bands[1] - bands[0])  ) /
                #   (bands[1] + (bands[0] * _EVI_C1) - (bands[2] * _EVI_C2)
                #    + _EVI_L)
                #   * _EVI_G)
                #tcbResult = np.clip(
                #    np.sum(bands * _TCB_COEFFS * _MODIS_SCALE_CONST, axis=0),
                #    0, 1)
                #tcwResult = np.clip(
                #    np.sum(bands * _TCW_COEFFS * _MODIS_SCALE_CONST, axis=0),
                #    0, 1)

                #byteScaled = bytescale(bands*_MODIS_SCALE_CONST, cmin=-0.01, cmax=1.10)
                #ndviResult = (bands[1] - bands[0]) / (bands[1] + bands[0]).astype('Float32')
                
            except:
                #print("evaluation of calculation %s failed" %(opts.calc))
                raise

            ndvInRelevantBands = np.any(myNDVs[[0,1,2]]==1,axis=0)
            # propogate nodata values
            # (set nodata cells to zero then add nodata value to these cells)

            if 1: #useNumExpr:
                eviResult = ne.evaluate("((1*(ndvInRelevantBands==0))*eviResult) + (OutputNDV*ndvInRelevantBands)")
                ndvInRelevantBands = np.any(myNDVs==1,axis=0)
                tcbResult = ne.evaluate("((1*(ndvInRelevantBands==0))*tcbResult) + (OutputNDV*ndvInRelevantBands)")
                tcwResult = ne.evaluate("((1*(ndvInRelevantBands==0))*tcwResult) + (OutputNDV*ndvInRelevantBands)")
            else:
                eviResult = ((1*(ndvInRelevantBands==0))*eviResult) + (OutputNDV*ndvInRelevantBands)
                ndvInRelevantBands = np.any(myNDVs==1,axis=0)
                tcbResult = ((1*(ndvInRelevantBands==0))*tcbResult) + (OutputNDV*ndvInRelevantBands)
                tcwResult = ((1*(ndvInRelevantBands==0))*tcwResult) + (OutputNDV*ndvInRelevantBands)

            # write data block to the output file
            eviOutB=eviOut.GetRasterBand(1)
            tcbOutB=tcbOut.GetRasterBand(1)
            tcwOutB=tcwOut.GetRasterBand(1)
            eviOutB.WriteArray(eviResult, xoff=myX, yoff=myY)
            tcbOutB.WriteArray(tcbResult, xoff=myX, yoff=myY)
            tcwOutB.WriteArray(tcwResult, xoff=myX, yoff=myY)

    print ("100 - Done")
    return

def main():
    usage = "usage: %prog [--B1 <filename>] ... [--B7 <filename>] [--EVIFile <filename>] [--TCBFile <filename>] [--TCWFile <filename>]"
    parser = OptionParser(usage)


    parser.add_option("--B1", dest="B1", help="mosaiced band 1 file (vrt)")
    parser.add_option("--B2", dest="B2", help="mosaiced band 2 file (vrt)")
    parser.add_option("--B3", dest="B3", help="mosaiced band 3 file (vrt)")
    parser.add_option("--B4", dest="B4", help="mosaiced band 4 file (vrt)")
    parser.add_option("--B5", dest="B5", help="mosaiced band 5 file (vrt)")
    parser.add_option("--B6", dest="B6", help="mosaiced band 6 file (vrt)")
    parser.add_option("--B7", dest="B7", help="mosaiced band 7 file (vrt)")

    parser.add_option("--EVIFile", dest="eviOutputFN", help="output EVI file to generate or fill")
    parser.add_option("--TCBFile", dest="tcbOutputFN", help="output EVI file to generate or fill")
    parser.add_option("--TCWFile", dest="tcwOutputFN", help="output EVI file to generate or fill")

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
    elif not (opts.B1 and opts.B2 and opts.B3 and opts.B4 and opts.B5 and opts.B6 and opts.B7
            and opts.eviOutputFN and opts.tcbOutputFN and opts.tcwOutputFN):
        print("No calculation provided.  Nothing to do!")
        parser.print_help()
    else:
        doit(opts, args)
    sys.exit(0)

if __name__ == '__main__':
    main()

