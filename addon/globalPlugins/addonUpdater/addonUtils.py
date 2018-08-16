# Add-on Updater
# Copyright 2018 Joseph Lee, released under GPL.

from urllib import urlopen
import ctypes
import ssl
import cPickle as pickle
import os
import globalVars

updateState = {}

def loadState():
	global updateState
	try:
		updateState = pickle.load(file(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "r"))
	except (IOError, EOFError):
		updateState["autoUpdate"] = True
		updateState["lastChecked"] = 0
		updateState["noUpdates"] = []
	# Just to make sure...
	if "autoUpdate" not in updateState: updateState["autoUpdate"] = True
	if "lastChecked" not in updateState: updateState["lastChecked"] = 0
	if "noUpdates" not in updateState: updateState["noUpdates"] = []

def saveState():
	global updateState
	try:
		pickle.dump(updateState, file(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "wb"))
	except IOError:
		pass
	updateState= None


# Borrowed from NVDA Core (the only difference is the URL and where structures are coming from).
def _updateWindowsRootCertificates():
	crypt = ctypes.windll.crypt32
	# Get the server certificate.
	sslCont = ssl._create_unverified_context()
	u = urlopen("https://addons.nvda-project.org", context=sslCont)
	cert = u.fp._sock.getpeercert(True)
	u.close()
	# Convert to a form usable by Windows.
	certCont = crypt.CertCreateCertificateContext(
		0x00000001, # X509_ASN_ENCODING
		cert,
		len(cert))
	# Ask Windows to build a certificate chain, thus triggering a root certificate update.
	chainCont = ctypes.c_void_p()
	crypt.CertGetCertificateChain(None, certCont, None, None,
		ctypes.byref(updateCheck.CERT_CHAIN_PARA(cbSize=ctypes.sizeof(updateCheck.CERT_CHAIN_PARA),
			RequestedUsage=updateCheck.CERT_USAGE_MATCH())),
		0, None,
		ctypes.byref(chainCont))
	crypt.CertFreeCertificateChain(chainCont)
	crypt.CertFreeCertificateContext(certCont)
