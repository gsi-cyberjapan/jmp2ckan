# -*- coding: utf-8 -*-
# Copyright 2014, Geospatial Information Authority of Japan, released
# under the FreeBSD license. Please see

import ckanclient
import locale
import ConfigParser
import os
import sys
import xml.dom
import xml.dom.minidom
import codecs
import xmltodict
import json
import string
import random
import logging
import logging.config
import datetime
import urllib
import shutil

from xml.dom import minidom
from subprocess import Popen, PIPE
from collections import defaultdict

sys.stdout = codecs.getwriter("UTF-8")(sys.stdout)


# コンフィグディレクトリ
CONFIG_DIR = "config/"

toolConfig = ConfigParser.SafeConfigParser()
toolConfig.read(CONFIG_DIR + "tool.prop")

codeConfig = ConfigParser.SafeConfigParser()
codeConfig.read(CONFIG_DIR + "codelist.prop")

itemConfig = ConfigParser.SafeConfigParser()
itemConfig.read(CONFIG_DIR + "screenItem.prop")

organizationConfig = ConfigParser.SafeConfigParser()
organizationConfig.read(CONFIG_DIR + "organization.prop")

spatialConfig = ConfigParser.SafeConfigParser()
spatialConfig.read(CONFIG_DIR + "spatial.prop")

# 現在タイムスタンプを生成
now = datetime.datetime.now()
nowtime = now.strftime("%Y%m%d%H%M%S")

# 出力のフォーマットを定義
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")

# ログレベル設定
log_level = toolConfig.get("Log", "log_level")
if log_level == "CRITICAL":
	logging.basicConfig(level=logging.CRITICAL)
elif log_level == "ERROR":
	logging.basicConfig(level=logging.ERROR)
elif log_level == "WARNING":
	logging.basicConfig(level=logging.WARNING)
elif log_level == "INFO":
	logging.basicConfig(level=logging.INFO)
elif log_level == "DEBUG":
	logging.basicConfig(level=logging.DEBUG)
elif log_level == "NOTSET":
	logging.basicConfig(level=logging.NOTSET)

# ログハンドラ
logger1 = logging.getLogger("root")
logger2 = logging.getLogger("error")

# ログディレクトリ
log_dir = toolConfig.get("Directory", "log_dir")
logger1.debug("log_dir : " + log_dir)
if os.path.isdir(log_dir) == False:
	os.mkdir(log_dir)

# ファイルへ出力するハンドラを定義
rootHandler = logging.FileHandler(filename=toolConfig.get("Directory", "log_dir") + "/" + nowtime + ".log")
rootHandler.setFormatter(formatter)
errorHandler = logging.FileHandler(filename=toolConfig.get("Directory", "log_dir") + "/" + "error_" + nowtime + ".log")
errorHandler.setFormatter(formatter)

# ロガーにハンドラを登録
logger1.addHandler(rootHandler)
logger2.addHandler(errorHandler)

# ckanclientのインスタンス生成
ckan = ckanclient.CkanClient(base_location=toolConfig.get("Server", "api_url"),
							 api_key=toolConfig.get("User", "api_key"))

# 対象XMLディレクトリ取得
argvs = sys.argv
argc = len(argvs)
if (argc != 2):
    print u"引数の指定が誤っています。"
    quit()
    
xml_dir = argvs[1]
logger1.debug("xml_dir : " + xml_dir)
if xml_dir[-1] == "/":
	xml_dir = xml_dir[:-1]

logger1.debug("xml_dir : " + xml_dir)


# ==============================================================================
#
# 表示ラベル名取得
#
def getLabel(key):
	return itemConfig.get("Label", key)
# ==============================================================================
#
# 測地系の表記揺れを統一
#
def replaceAmbiguousString(code):
	code = code.replace(u" ", "")
	code = code.replace(u"　", "")
	code = code.replace(u"，", ",")
	code = code.replace(u".", ",")
	code = code.replace(u"．", ",")
	code = code.replace(u"／", "/")
	code = code.replace(u"（", "(")
	code = code.replace(u"）", ")")
	return code
# ==============================================================================
#
# 地理情報設定
#
def setSpatialData(package, extent):
	
	logger1.debug("setSpatialData start")
	
	spatial = {}
	west = None
	east = None
	south = None
	north = None
	datumCode = ""
	
	polygon_flg = 0
	
	strJgdDatum = spatialConfig.has_option("Datum", "JGD2000/(B,L)")
	
	# 地理要素チェック
	if extent["geographicElement"].has_key("EX_GeographicBoundingBox"):
		# 地理境界ボックスあり
		geos = extent["geographicElement"]["EX_GeographicBoundingBox"]
		if isinstance(geos, list):
			logger1.debug("EX_GeographicBoundingBox - list")
			for i, geo in enumerate(geos):
				if geo.has_key("extentReferenceSystem"):
					if geo["extentReferenceSystem"].has_key("code"):
						tmpDatumCode = replaceAmbiguousString(geo["extentReferenceSystem"]["code"])
						if (datumCode == "") or (tmpDatumCode == strJgdDatum and geo.has_key("westBoundLongitude")) or ((datumCode != strJgdDatum) and (spatialConfig.has_option("Datum", tmpDatumCode.encode("UTF-8")) == True)):
							datumCode = tmpDatumCode
							if geo.has_key("westBoundLongitude") and geo.has_key("eastBoundLongitude") and geo.has_key("southBoundLatitude") and geo.has_key("northBoundLatitude"):
								west  = geo["westBoundLongitude"]
								east  = geo["eastBoundLongitude"]
								south = geo["southBoundLatitude"]
								north = geo["northBoundLatitude"]
		else:
			logger1.debug("EX_GeographicBoundingBox - not list")
			if geos.has_key("extentReferenceSystem"):
				if geos["extentReferenceSystem"].has_key("code"):
					datumCode = replaceAmbiguousString(geos["extentReferenceSystem"]["code"])
					if geos.has_key("westBoundLongitude") and geos.has_key("eastBoundLongitude") and geos.has_key("southBoundLatitude") and geos.has_key("northBoundLatitude"):
						west  = geos["westBoundLongitude"]
						east  = geos["eastBoundLongitude"]
						south = geos["southBoundLatitude"]
						north = geos["northBoundLatitude"]
	elif extent["geographicElement"].has_key("EX_CoordinateBoundingBox"):
		# 座標境界ボックスあり
		geos = extent["geographicElement"]["EX_CoordinateBoundingBox"]
		if isinstance(geos, list):
			logger1.debug("EX_CoordinateBoundingBox - list")
			for i, geo in enumerate(geos):
				if geo.has_key("extentReferenceSystem"):
					if geo["extentReferenceSystem"].has_key("code"):
						tmpDatumCode = replaceAmbiguousString(geo["extentReferenceSystem"]["code"])
						if (datumCode == "") or (spatialConfig.has_option("Datum", tmpDatumCode.encode("UTF-8")) == True):
							datumCode = tmpDatumCode
							if geo.has_key("westBoundCoordinate") and geo.has_key("eastBoundCoordinate") and geo.has_key("southBoundCoordinate") and geo.has_key("northBoundCoordinate"):
								west  = geo["westBoundCoordinate"]
								east  = geo["eastBoundCoordinate"]
								south = geo["southBoundCoordinate"]
								north = geo["northBoundCoordinate"]
		else:
			logger1.debug("EX_CoordinateBoundingBox - not list")
			if geos.has_key("extentReferenceSystem"):
				if geos["extentReferenceSystem"].has_key("code"):
					datumCode = replaceAmbiguousString(geos["extentReferenceSystem"]["code"])
					if geos.has_key("westBoundCoordinate") and geos.has_key("eastBoundCoordinate") and geos.has_key("southBoundCoordinate") and geos.has_key("northBoundCoordinate"):
						west  = geos["westBoundCoordinate"]
						east  = geos["eastBoundCoordinate"]
						south = geos["southBoundCoordinate"]
						north = geos["northBoundCoordinate"]
			
	elif extent["geographicElement"].has_key("EX_BoundingPolygon"):
		# 境界ポリゴンあり
		geos = extent["geographicElement"]["EX_BoundingPolygon"]
		if isinstance(geos, list):
			logger1.debug("EX_BoundingPolygon - list")
			for i, geo in enumerate(geos):
				if geo.has_key("extentReferenceSystem"):
					if geo["extentReferenceSystem"].has_key("code"):
						datumCode = replaceAmbiguousString(geo["extentReferenceSystem"]["code"])
						coordinates  = geo["polygon"]["polygon"]["exterior"]["LinearRing"]["coordinates"]
		else:
			logger1.debug("EX_BoundingPolygon - not list")
			if geos.has_key("extentReferenceSystem"):
				if geos["extentReferenceSystem"].has_key("code"):
					datumCode = replaceAmbiguousString(geos["extentReferenceSystem"]["code"])
					coordinates  = geos["polygon"]["polygon"]["exterior"]["LinearRing"]["coordinates"]
		polygon_flg = 1
		logger1.debug("*** Only Polygon ***")
		logger1.debug("coordinates : " + coordinates)
	
	if polygon_flg == 0:
		if (spatialConfig.has_option("Datum", datumCode.encode("UTF-8")) == False) or (datumCode == "") or (datumCode == None) or (west == None) or (east == None) or (south == None) or (north == None):
			logger1.debug("no spatial data")
			return
		
		logger1.debug("DatumCode : " + datumCode)
		logger1.debug("west : " + west)
		logger1.debug("east : " + east)
		logger1.debug("south : " + south)
		logger1.debug("north : " + north)
		
		# コードリストから取得
		fromDatum = spatialConfig.get("Datum", datumCode.encode("UTF-8"))
		logger1.debug("fromDatum : " + fromDatum)
		
		fromEpsg = spatialConfig.get("EPSG", fromDatum)
		logger1.debug("fromEpsg : " + fromEpsg)
		
		# PolygonかPointか判定
		if west != east:
			spatial["type"] = "Polygon"
			if (fromEpsg != "4612"):
				logger1.debug("Polygon : " + fromEpsg + " -> 4612")
				p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
					stdin=PIPE, stdout=PIPE, universal_newlines=True)
				ret1 = p.communicate("%s %s\n" % (west, south))[0].split(" ")
				p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
					stdin=PIPE, stdout=PIPE, universal_newlines=True)
				ret2 = p.communicate("%s %s\n" % (west, north))[0].split(" ")
				p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
					stdin=PIPE, stdout=PIPE, universal_newlines=True)
				ret3 = p.communicate("%s %s\n" % (east, north))[0].split(" ")
				p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
					stdin=PIPE, stdout=PIPE, universal_newlines=True)
				ret4 = p.communicate("%s %s\n" % (east, south))[0].split(" ")
				spatial["coordinates"] = [ [ [float(ret1[0]), float(ret1[1])], \
											[float(ret2[0]), float(ret2[1])], \
											[float(ret3[0]), float(ret3[1])], \
											[float(ret4[0]), float(ret4[1])] ] ]
			else:
				logger1.debug("Polygon : 4612 -> 4612")
				spatial["coordinates"] = [ [ [float(west), float(south)], \
											[float(west), float(north)], \
											[float(east), float(north)], \
											[float(east), float(south)] ] ]
		else:
			spatial["type"] = "Point"
			if (fromEpsg != 4612):
				logger1.debug("Point : " + fromEpsg + " -> 4612")
				p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
					stdin=PIPE, stdout=PIPE, universal_newlines=True)
				ret = p.communicate("%s %s\n" % (south, west))[0].split(" ")
				spatial["coordinates"] = [float(ret[1]), float(ret[0])]
			else:
				logger1.debug("Point : 4612 -> 4612")
				spatial["coordinates"] = [west, south]
	else:
		logger1.debug("DatumCode : " + datumCode)
		logger1.debug("coordinates : " + coordinates)
		
		# コードリストから取得
		fromDatum = spatialConfig.get("Datum", datumCode.encode("UTF-8"))
		logger1.debug("fromDatum : " + fromDatum)
		
		fromEpsg = spatialConfig.get("EPSG", fromDatum)
		logger1.debug("Polygon : " + fromEpsg + " -> 4612")
		
		coordinate = coordinates.split(" ")
		coordinate_list = []
		for values in coordinate:
			logger1.debug("values : " + values)
			value = values.split(",")
			logger1.debug("value[0] : " + value[0])
			logger1.debug("value[1] : " + value[1])
			p = Popen(["gdaltransform", "-s_srs", "EPSG:" + fromEpsg, "-t_srs", "EPSG:4612"],
				stdin=PIPE, stdout=PIPE, universal_newlines=True)
			ret = p.communicate("%s %s\n" % (value[0], value[1]))[0].split(" ")
			logger1.debug("ret[0] : " + ret[0])
			logger1.debug("ret[1] : " + ret[1])
			
			values = [float(ret[0]), float(ret[1])]
			coordinate_list.append(values)
			
		spatial["type"] = "Polygon"
		spatial["coordinates"] = [ coordinate_list ]
		logger1.debug(coordinate_list)
		
	package["extras"]["spatial"] = json.dumps(spatial, ensure_ascii = False)
	
	logger1.debug("setSpatial end")
	
# ==============================================================================
#
# 組織情報設定
#
def setOrganization(package, doc, targetDirectory):
	
	logger1.debug("setOrganization start")
	logger1.debug("targetDirectory : " + targetDirectory)
	
	# フォルダ単位で指定されているかどうかチェック
	if organizationConfig.has_option("FolderName", targetDirectory):
		logger1.debug("organization - Folder")
		orgName = unicode(organizationConfig.get("FolderName", targetDirectory), "UTF-8")
		ckanName = unicode(organizationConfig.get("CkanName", orgName.encode("UTF-8")), "UTF-8")
		package["owner_org"] = ckanName
	else:
		logger1.debug("organization - File")
		jmpName = unicode(organizationConfig.get("JmpName", doc["MD_Metadata"]["contact"]["organisationName"].encode("UTF-8")), "UTF-8")
		ckanName = unicode(organizationConfig.get("CkanName", jmpName.encode("UTF-8")), "UTF-8")
		package["owner_org"] = ckanName
	logger1.debug("owner_org : " + package["owner_org"])
	
	logger1.debug("setOrganization end")
	
# ==============================================================================
#
# 識別情報設定
#
def setIdentificationInfo(package, doc, idInfo):

	logger1.debug("setIdentificationInfo start")
	
	# タイトル
	package["title"] = idInfo["citation"]["title"]
	logger1.debug("title : " + package["title"])
	
	# 説明
	abstractStr = ""
	purposeStr = ""
	dateStr = ""
	## 要約
	abstractStr = "##" + unicode(itemConfig.get("Label", "notes.abstract"), "UTF-8") + "\n" + idInfo["abstract"]
	logger1.debug("abstract")
	## 目的
	if idInfo.has_key("purpose"):
		purposeStr = "\n##" + unicode(itemConfig.get("Label", "notes.purpose"), "UTF-8") + "\n" + idInfo["purpose"]
		logger1.debug("purpose")
	## 日付
	if idInfo["citation"].has_key("date"):
		dates = idInfo["citation"]["date"]
		if isinstance(dates, list):
			for date in dates:
				dateStr += "\n##" + unicode(codeConfig.get("DateType", date["dateType"]), "UTF-8") + "\n" + date["date"]
		else:
			dateStr = "\n##" + unicode(codeConfig.get("DateType", dates["dateType"]), "UTF-8") + "\n" + dates["date"]
		logger1.debug("date")
	package["notes"] = abstractStr + purposeStr + dateStr
	logger1.debug("notes : " + package["notes"])
	
	# タグ
	if idInfo.has_key("topicCategory"):
		tags = idInfo["topicCategory"]
		if isinstance(tags, list):
			logger1.debug("topicCategory - list")
			for i, tag in enumerate(tags):
				tags[i] = unicode(codeConfig.get("TopicCategory", tag), "UTF-8")
				package["tags"] = tags
				package["extras"][getLabel("topicCategory")] = ",".join(tags)
		else:
			logger1.debug("topicCategory - not list")
			package["tags"] = unicode(codeConfig.get("TopicCategory", tags), "UTF-8")
			package["extras"][getLabel("topicCategory")] = unicode(codeConfig.get("TopicCategory", tags), "UTF-8")
		logger1.debug("topicCategory : " + package["extras"][getLabel("topicCategory")])
	
	# ステータス
	if idInfo.has_key("status"):
		statuses = idInfo["status"]
		if isinstance(statuses, list):
			logger1.debug("status - list")
			for i, status in enumerate(statuses):
				statuses[i] = unicode(codeConfig.get("Progress", status), "UTF-8")
			package["extras"][getLabel("status")] = ",".join(statuses)
		else:
			logger1.debug("status - not list")
			package["extras"][getLabel("status")] = codeConfig.get("Progress", statuses)
		logger1.debug("status : " + package["extras"][getLabel("status")])
	
	# 問合せ先[連番]
	if idInfo.has_key("pointOfContact"):
		contacts = idInfo["pointOfContact"]
		if isinstance(contacts, list):
			logger1.debug("contacts - list")
			for i, contact in enumerate(contacts):
				package["extras"][getLabel("pointOfContact") + str(i + 1)] = json.dumps(contact, ensure_ascii = False)
				logger1.debug("contact" + str(i + 1) + " : " + package["extras"][getLabel("pointOfContact") + str(i + 1)])
		else:
			logger1.debug("contacts - not list")
			package["extras"][getLabel("pointOfContact") + "1"] = json.dumps(contacts, ensure_ascii = False)
			logger1.debug("contact1 : " + package["extras"][getLabel("pointOfContact") + "1"])
	
	# 概要の図示
	if idInfo.has_key("graphicOverview"):
		package["extras"][getLabel("graphicOverview")] = json.dumps(idInfo["graphicOverview"], ensure_ascii = False)
		logger1.debug("graphicOverview : " + package["extras"][getLabel("graphicOverview")])
	
	# 記述的キーワード
	if idInfo.has_key("descriptiveKeywords"):
		if idInfo["descriptiveKeywords"].has_key("MD_Keywords"):
			package["extras"][getLabel("descriptiveKeywords")] = json.dumps(idInfo["descriptiveKeywords"]["MD_Keywords"], ensure_ascii = False)
			logger1.debug("descriptiveKeywords : " + package["extras"][getLabel("descriptiveKeywords")])
	
	# 情報資源の制約
	if idInfo.has_key("resourceConstraints"):
		if idInfo["resourceConstraints"].has_key("MD_Constraints"):
			package["extras"][getLabel("resourceConstraints")] = json.dumps(idInfo["resourceConstraints"], ensure_ascii = False)
			logger1.debug("resourceConstraints : " + package["extras"][getLabel("resourceConstraints")])
	
	# 空間表現型
	if idInfo.has_key("spatialRepresentationType"):
		spatialTypes = idInfo["spatialRepresentationType"]
		if isinstance(spatialTypes, list):
			logger1.debug("spatialTypes - list")
			for i, spatialType in enumerate(spatialTypes):
				spatialTypes[i] = unicode(codeConfig.get("SpatialRepresentationType", spatialType), "UTF-8")
			package["extras"][getLabel("spatialRepresentationType")] = ",".join(spatialTypes)
		else:
			logger1.debug("spatialTypes - not list")
			package["extras"][getLabel("spatialRepresentationType")] = unicode(codeConfig.get("SpatialRepresentationType", spatialTypes), "UTF-8")
		logger1.debug("spatialRepresentationType : " + package["extras"][getLabel("spatialRepresentationType")])
	
	# 空間解像度
	if idInfo.has_key("spatialResolution"):
		spatialResolutions = idInfo["spatialResolution"]
		package["extras"][getLabel("spatialResolution")] = json.dumps(spatialResolutions, ensure_ascii = False)
		logger1.debug("spatialResolution : " + package["extras"][getLabel("spatialResolution")])
	
	# 識別情報-言語
	if idInfo.has_key("language"):
		idLanguages = idInfo["language"]
		if isinstance(idLanguages, list):
			logger1.debug("idLanguage - list")
			for i, idLanguage in enumerate(idLanguages):
				idLanguages[i] = unicode(codeConfig.get("Language", idLanguage["isoCode"]), "UTF-8")
			package["extras"][getLabel("idLanguage")] = ",".join(idLanguages)
		else:
			logger1.debug("idLanguage - not list")
			package["extras"][getLabel("idLanguage")] = unicode(codeConfig.get("Language", idLanguages["isoCode"]), "UTF-8")
#		logger1.debug("idLanguage : " + package["extras"][getLabel("idLanguage")])
	
	# 識別情報-文字集合
	if idInfo.has_key("characterSet"):
		idCharacterSets = idInfo["characterSet"]
		if isinstance(idCharacterSets, list):
			logger1.debug("idCharacterSet - list")
			for i, idCharacterSet in enumerate(idCharacterSets):
				idCharacterSets[i] = unicode(codeConfig.get("CharacterSet", idCharacterSet), "UTF-8")
				package["extras"][getLabel("idCharacterSet")] = ",".join(idCharacterSets)
		else:
			logger1.debug("idCharacterSet - not list")
			package["extras"][getLabel("idCharacterSet")] = unicode(codeConfig.get("CharacterSet", idCharacterSets), "UTF-8")
#		logger1.debug("idCharacterSet : " + package["extras"][getLabel("idCharacterSet")])
	
	# 識別情報-範囲
	if idInfo.has_key("extent"):
		extents = idInfo["extent"]
		if isinstance(extents, list):
			logger1.debug("idExtent - list")
			for i, extent in enumerate(extents):
				# 記述
				if extent.has_key("description"):
					package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentDescription")] = extent["description"]
					logger1.debug("idExtent" + str(i + 1) + "-description : " + package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentDescription")])
				# 地理要素
				if extent.has_key("geographicElement"):
					package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentGeographicElement")] = json.dumps(extent["geographicElement"], ensure_ascii = False)
					logger1.debug("idExtent" + str(i + 1) + "-geographicElement : " + package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentGeographicElement")])
				# 時間要素
				if extent.has_key("temporalElement"):
					package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentTemporalElement")] = json.dumps(extent["temporalElement"], ensure_ascii = False)
					logger1.debug("idExtent" + str(i + 1) + "-temporalElement : " + package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentTemporalElement")])
				# 垂直要素
				if extent.has_key("verticalElement"):
					package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentVerticalElement")] = json.dumps(extent["verticalElement"], ensure_ascii = False)
					logger1.debug("idExtent" + str(i + 1) + "-verticalElement : " + package["extras"][getLabel("idExtent") + str(i + 1) + "-" + getLabel("idExtentVerticalElement")])
		else:
			logger1.debug("idExtent - not list")
			# 記述
			if extents.has_key("description"):
				package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentDescription")] = json.dumps(extents["description"], ensure_ascii = False)
				logger1.debug("idExtent1-description : " + package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentDescription")])
			# 地理要素
			if extents.has_key("geographicElement"):
				package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentGeographicElement") + "1"] = json.dumps(extents["geographicElement"], ensure_ascii = False)
				logger1.debug("idExtent1-geographicElement : " + package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentGeographicElement") + "1"])
			# 時間要素
			if extents.has_key("temporalElement"):
				package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentTemporalElement") + "1"] = json.dumps(extents["temporalElement"], ensure_ascii = False)
				logger1.debug("idExtent1-temporalElement : " + package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentTemporalElement") + "1"])
			# 垂直要素
			if extents.has_key("verticalElement"):
				package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentVerticalElement") + "1"] = json.dumps(extents["verticalElement"], ensure_ascii = False)
				logger1.debug("idExtent1-verticalElement : " + package["extras"][getLabel("idExtent") + "1-" + getLabel("idExtentVerticalElement") + "1"])
	
	logger1.debug("setIdentificationInfo end")
	
# ==============================================================================
#
# 品質情報設定
#
def setDataQualityInfo(package, doc, info, i):

	logger1.debug("setDataQualityInfo start")
	
	# 品質情報
	dqLabel = getLabel("dataQualityInfo")
	
	# 適用範囲
	if info.has_key("scope"):
		logger1.debug("scope")
		scope = info["scope"]
		if scope.has_key("DQ_Scope"):
			scope = scope["DQ_Scope"]
		# レベル
		if scope.has_key("level"):
			logger1.debug("level")
			package["extras"][dqLabel + str(i) + "-" + getLabel("dqLevel")] = codeConfig.get("Scope", scope["level"])
			logger1.debug("dqInfo" + str(i) + "-level : " + package["extras"][dqLabel + str(i) + "-" + getLabel("dqLevel")])
		# 範囲
		if scope.has_key("extent"):
			logger1.debug("extent")
			dqExtent = scope["extent"]
			dqExtentLabel = getLabel("dqExtent")
			# 記述
			if dqExtent.has_key("description"):
				package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqDescription")] = dqExtent["description"]
				logger1.debug("dqInfo" + str(i) + "-extent-description : " + package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqDescription")])
			# 地理要素
			if dqExtent.has_key("geographicElement"):
				package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentGeographicElement")] = json.dumps(dqExtent["geographicElement"], ensure_ascii = False)
				logger1.debug("dqInfo" + str(i) + "-extent-geographicElement : " + package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentGeographicElement")])
			# 時間要素
			if dqExtent.has_key("temporalElement"):
				package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentTemporalElement")] = json.dumps(dqExtent["temporalElement"], ensure_ascii = False)
				logger1.debug("dqInfo" + str(i) + "-extent-temporalElement : " + package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentTemporalElement")])
			# 垂直要素
			if dqExtent.has_key("verticalElement"):
				package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentVerticalElement")] = json.dumps(dqExtent["verticalElement"], ensure_ascii = False)
				logger1.debug("dqInfo" + str(i) + "-extent-verticalElement : " + package["extras"][dqLabel + str(i) + "-" + dqExtentLabel + getLabel("dqExtentVerticalElement")])
		# レベル記述
		if scope.has_key("levelDescription"):
			levelDescriptions = scope["levelDescription"]
			if isinstance(levelDescriptions, list):
				logger1.debug("levelDescription - list")
				package["extras"][dqLabel + str(i) + "-" + getLabel("dqLevelDescription")] = ",".join(levelDescriptions)
			else:
				logger1.debug("levelDescription - not list")
				package["extras"][dqLabel + str(i) + "-" + getLabel("dqLevelDescription")] = levelDescriptions
			logger1.debug("dqInfo" + str(i) + "-levelDescription : " + package["extras"][dqLabel + str(i) + "-" + getLabel("dqLevelDescription")])
	# 報告
	if info.has_key("report"):
		logger1.debug("report")
		reports = info["report"]
		package["extras"][dqLabel + str(i) + "-" + getLabel("dqReport")] = json.dumps(reports, ensure_ascii = False)
		logger1.debug("dqInfo" + str(i) + "-report : " + package["extras"][dqLabel + str(i) + "-" + getLabel("dqReport")])
	# 系譜
	if info.has_key("lineage"):
		logger1.debug("lineage")
		lineage = info["lineage"]
		package["extras"][dqLabel + str(i) + "-" + getLabel("dqLineage")] = json.dumps(lineage, ensure_ascii = False)
		logger1.debug("dqInfo" + str(i) + "-lineage : " + package["extras"][dqLabel + str(i) + "-" + getLabel("dqLineage")])

#	else:
#		logger1.debug("dataQualityInfo - not list")
#		# 適用範囲
#		if dqInfo.has_key("scope"):
#			scope = dqInfo["scope"]
#			# レベル
#			if scope.has_key("level"):
#				package["extras"][dqLabel + "1-" + getLabel("dqLevel")] = codeConfig.get("Scope", scope["level"])
#				logger1.debug("dqInfo1-level : " + package["extras"][dqLabel + "1-" + getLabel("dqLevel")])
#			# 範囲
#			if scope.has_key("extent"):
#				dqExtent = scope["extent"]
#				dqExtentLabel = getLabel("dqExtent")
#				# 記述
#				if dqExtent.has_key("description"):
#					package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqDescription")] = dqExtent["description"]
#					logger1.debug("dqInfo1-extent-description : " + package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqDescription")])
#				# 地理要素
#				if dqExtent.has_key("geographicElement"):
#					package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentGeographicElement")] = json.dumps(dqExtent["geographicElement"], ensure_ascii = False)
#					logger1.debug("dqInfo1-extent-geographicElement : " + package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentGeographicElement")])
#				# 時間要素
#				if dqExtent.has_key("temporalElement"):
#					package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentTemporalElement")] = json.dumps(dqExtent["temporalElement"], ensure_ascii = False)
#					logger1.debug("dqInfo1-extent-temporalElement : " + package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentTemporalElement")])
#				# 垂直要素
#				if dqExtent.has_key("verticalElement"):
#					package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentVerticalElement")] = json.dumps(dqExtent["verticalElement"], ensure_ascii = False)
#					logger1.debug("dqInfo1-extent-verticalElement : " + package["extras"][dqLabel + "1-" + dqExtentLabel + getLabel("dqExtentVerticalElement")])
#			# レベル記述
#			if scope.has_key("levelDescription"):
#				levelDescriptions = scope["levelDescription"]
#				if isinstance(levelDescriptions, list):
#					logger1.debug("levelDescription - list")
#					package["extras"][dqLabel + "1-" + getLabel("dqLevelDescription")] = ",".join(levelDescriptions)
#				else:
#					logger1.debug("levelDescription - not list")
#					package["extras"][dqLabel + "1-" + getLabel("dqLevelDescription")] = levelDescriptions
#				logger1.debug("dqInfo1-levelDescription : " + package["extras"][dqLabel + "1-" + getLabel("dqLevelDescription")])
#		# 報告
#		if dqInfo.has_key("report"):
#			reports = dqInfo["report"]
#			package["extras"][dqLabel + "1-" + getLabel("dqReport")] = json.dumps(reports, ensure_ascii = False)
#			logger1.debug("dqInfo1-report : " + package["extras"][dqLabel + "1-" + getLabel("dqReport")])
#		# 系譜
#		if dqInfo.has_key("lineage"):
#			lineage = dqInfo["lineage"]
#			package["extras"][dqLabel + "1-" + getLabel("dqLineage")] = json.dumps(lineage, ensure_ascii = False)
#			logger1.debug("dqInfo1-lineage : " + package["extras"][dqLabel + "1-" + getLabel("dqLineage")])

	logger1.debug("setDataQualityInfo end")
	
# ==============================================================================
#
# データセット登録
#
def registerPackage(root, file, doc):
	
	# ターゲットフォルダ
	logger1.debug("root : " + root)
	logger1.debug("xml_dir : " + xml_dir)
	targetDirectory = root.replace(xml_dir + "/", "")
	logger1.debug("targetDirectory : " + targetDirectory)
	
	# 配列初期化
	package = defaultdict(lambda:defaultdict(lambda:defaultdict(dict)))
	
	# 名前
	name = ""
	while name == "":
		try:
			temp_name = "".join([random.choice(string.ascii_lowercase + string.digits) for i in range(8)])
			logger1.debug("temp_name : " + temp_name)
			ckan.package_entity_get(temp_name)
		except:
			logger1.debug("name does not exists")
			name = temp_name
	package["name"] = name
	logger1.debug("name : " + package["name"])
	
	# 組織と紐付け
	setOrganization(package, doc, targetDirectory)
	logger1.debug("organization : " + package["owner_org"])
	
	# ライセンス
	package["license_id"] = "notspecified"
	logger1.debug("license_id : " + package["license_id"])
	
	# ファイル識別子
	if doc["MD_Metadata"].has_key("fileIdentifier"):
		package["extras"][getLabel("fileIdentifier")] = doc["MD_Metadata"]["fileIdentifier"]
		logger1.debug("fileIdentifier : " + package["extras"][getLabel("fileIdentifier")])
	
	# 言語
	if doc["MD_Metadata"].has_key("language"):
		package["extras"][getLabel("language")] = codeConfig.get("Language", doc["MD_Metadata"]["language"]["isoCode"])
		logger1.debug("language : " + package["extras"][getLabel("language")])
	
	# 文字集合
	if doc["MD_Metadata"].has_key("characterSet"):
		package["extras"][getLabel("characterSet")] = codeConfig.get("CharacterSet", doc["MD_Metadata"]["characterSet"])
		logger1.debug("characterSet : " + package["extras"][getLabel("characterSet")])
	
	# 親識別子
	if doc["MD_Metadata"].has_key("parentIdentifier"):
		package["extras"][getLabel("parentIdentifier")] = doc["MD_Metadata"]["parentIdentifier"]
		logger1.debug("parentIdentifier : " + package["extras"][getLabel("parentIdentifier")])
	
	# 階層レベル
	if doc["MD_Metadata"].has_key("hierarchyLevel"):
		levels = doc["MD_Metadata"]["hierarchyLevel"]
		if isinstance(levels, list):
			logger1.debug("hierarchyLevel - list")
			for i, level in enumerate(levels):
				levels[i] = codeConfig.get("Scope", level)
			package["extras"][getLabel("hierarchyLevel")] = ",".join(levels)
		else:
			logger1.debug("hierarchyLevel - not list")
			package["extras"][getLabel("hierarchyLevel")] = codeConfig.get("Scope", levels)
		logger1.debug("hierarchyLevel : " + package["extras"][getLabel("hierarchyLevel")])
	
	# 階層レベル名
	if doc["MD_Metadata"].has_key("hierarchyLevelName"):
		names = doc["MD_Metadata"]["hierarchyLevelName"]
		if isinstance(names, list):
			logger1.debug("hierarchyLevelName - list")
			package["extras"][getLabel("hierarchyLevelName")] = ",".join(names)
		else:
			logger1.debug("hierarchyLevelName - not list")
			package["extras"][getLabel("hierarchyLevelName")] = names
		logger1.debug("hierarchyLevelName : " + package["extras"][getLabel("hierarchyLevelName")])
	
	# 問合せ先（責任者）
	package["extras"][getLabel("contact")] = json.dumps(doc["MD_Metadata"]["contact"], ensure_ascii = False)
	logger1.debug("contact(Main) : " + package["extras"][getLabel("contact")])
	
	# 日付
	package["extras"][getLabel("dateStamp")] = doc["MD_Metadata"]["dateStamp"]
	logger1.debug("dateStamp : " + package["extras"][getLabel("dateStamp")])
	
	# メタデータ規格
	package["extras"][getLabel("metadataStandard")] = toolConfig.get("Tool", "jmp_version")
	logger1.debug("metadataStandard : " + package["extras"][getLabel("metadataStandard")])
	
	# 参照系情報
	if doc["MD_Metadata"].has_key("referenceSystemInfo"):
		package["extras"][getLabel("referenceSystemInfo")] = json.dumps(doc["MD_Metadata"]["referenceSystemInfo"], ensure_ascii = False)
		logger1.debug("referenceSystemInfo : " + package["extras"][getLabel("referenceSystemInfo")])
	
	# 識別情報セット
	idInfo = doc["MD_Metadata"]["identificationInfo"]["MD_DataIdentification"]
	setIdentificationInfo(package, doc, idInfo)
	
	# 配布情報
	if doc["MD_Metadata"].has_key("distributionInfo"):
		package["extras"][getLabel("distributionInfo")] = json.dumps(doc["MD_Metadata"]["distributionInfo"], ensure_ascii = False)
		logger1.debug("distributionInfo : " + package["extras"][getLabel("distributionInfo")])
	
	# 品質情報セット
	if doc["MD_Metadata"].has_key("dataQualityInfo"):
		dqInfo = doc["MD_Metadata"]["dataQualityInfo"]
		i = 0
		if isinstance(dqInfo, list):
			logger1.debug("dataQualityInfo - list")
			for info in dqInfo:
				inf = info["DQ_DataQuality"]
				if isinstance(inf, list):
					logger1.debug("inf - list")
					for dq in inf:
						i = i + 1
						logger1.debug("i : " + str(i))
						setDataQualityInfo(package, doc, dq, i)
				else:
					logger1.debug("inf - not list")
					i = i + 1
					logger1.debug("i : " + str(i))
					setDataQualityInfo(package, doc, inf, i)
		else:
			logger1.debug("dataQualityInfo - not list")
			dq = dqInfo["DQ_DataQuality"]
			if isinstance(dq, list):
				logger1.debug("dq - list")
				for d in dq:
					i = i + 1
					logger1.debug("i : " + str(i))
					setDataQualityInfo(package, doc, d, i)
			else:
				logger1.debug("dq - not list")
				i = i + 1
				logger1.debug("i : " + str(i))
				setDataQualityInfo(package, doc, dq, i)
	
	# 地理情報
	if idInfo.has_key("extent"):
		extents = idInfo["extent"]
		if isinstance(extents, list):
			for i, extent in enumerate(extents):
				# 地理要素
				if extent.has_key("geographicElement"):
					geographicElement = extent["geographicElement"]
					if geographicElement.has_key("EX_BoundingPolygon") or geographicElement.has_key("EX_GeographicBoundingBox") or geographicElement.has_key("EX_CoordinateBoundingBox"):
						setSpatialData(package, extent)
		else:
			# 地理要素
			if extents.has_key("geographicElement"):
				geographicElement = extents["geographicElement"]
				if geographicElement.has_key("EX_BoundingPolygon") or geographicElement.has_key("EX_GeographicBoundingBox") or geographicElement.has_key("EX_CoordinateBoundingBox"):
					setSpatialData(package, extents)
	
#	logger1.debug(package)
	
	# パッケージ登録
	ckan.package_register_post(package)
	logger1.debug("package_register_post OK")
	
	# リソース登録
	tmpFilePath = ""
	try:
		resourceName = file.replace(".xml", "")
		logger1.debug("resourceName : " + resourceName)
		
		filePath = root + "/" + file
		logger1.debug("filePath : " + filePath)
		
		tmpFilePath = toolConfig.get("Resource", "resource_tmp_dir") + "/" + name + "_" + toolConfig.get("Resource", "resource_tmp_file")
		shutil.copyfile(filePath, tmpFilePath)
		
		resource = ckan.upload_file(tmpFilePath)
		os.remove(tmpFilePath)
		logger1.debug("upload_file OK")
		
		ckan.add_package_resource(package["name"], \
									resourceName, \
									url=toolConfig.get("Server", "server_url") + resource[0], \
									name=resourceName, \
									resource_type="file.upload", \
									format="XML")
		logger1.debug("add_package_resource OK")
		
		# 処理成功ファイルを移動
		shutil.move(filePath, toolConfig.get("Directory", "ok_dir"))
	except:
		logger1.debug("resource NG")
		os.remove(tmpFilePath)
		os.system('paster --plugin=ckan dataset purge ' + name + ' --config=' + toolConfig.get("Resource", "production"))
		raise

# ==============================================================================
#
# メイン
#
if __name__ == "__main__":
	
	logger1.info("***** Data Transfer Start *****")
	
	# ファイル読み込み
	for root, dirs, files in os.walk(xml_dir):
		for file in files:
			try:
				doc = xmltodict.parse(minidom.parse(os.path.join(root, file)).toxml("UTF-8"))
				registerPackage(root, file, doc)
#				print "Success:" + os.path.join(root, unicode(file, "UTF-8"))
				logger1.info("Success : " + os.path.join(root, file))
			except:
#				print "Failed : " + os.path.join(root, unicode(file, "UTF-8"))
				logger2.error("Failed : " + os.path.join(root, file))
				logger2.error(sys.exc_info()[0])
	logger1.info("***** Data Transfer End *****")
