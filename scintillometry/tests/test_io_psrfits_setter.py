# Licensed under the GPLv3 - see LICENSE
"""Full-package tests of psrfits writing routines."""

import os

import pytest
import numpy as np
import shutil
from astropy.time import Time, TimeDelta
from astropy.coordinates import SkyCoord, EarthLocation
from astropy.coordinates import Angle, Latitude, Longitude
import astropy.units as u

from ..io import psrfits


test_data = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')


class TestWriter:
    def setup(self):
        self.fold_data = os.path.join(test_data,
                                      "B1855+09.430.PUPPI.11y.x.sum.sm")
        self.reader = psrfits.open(self.fold_data, weighted=False)
        self.input_p_hdu = self.reader.ih.primary_hdu
        # init Primary
        self.p_hdu = psrfits.PSRFITSPrimaryHDU()

    def teardown(self):
        self.reader.close()

    def test_set_location(self):
        self.p_hdu.location = self.input_p_hdu.location
        assert self.p_hdu.header['ANT_X'] == self.input_p_hdu.header['ANT_X']
        assert self.p_hdu.header['ANT_Y'] == self.input_p_hdu.header['ANT_Y']
        assert self.p_hdu.header['ANT_Z'] == self.input_p_hdu.header['ANT_Z']

    def test_set_telescope(self):
        self.p_hdu.telescope = self.input_p_hdu.telescope
        assert (self.p_hdu.header['TELESCOP'] ==
                self.input_p_hdu.header['TELESCOP'])

    def test_set_start_time(self):
        self.p_hdu.start_time = self.input_p_hdu.start_time
        assert np.isclose(int(self.p_hdu.header['STT_IMJD']),
                          self.input_p_hdu.header['STT_IMJD'])
        assert np.isclose(int(self.p_hdu.header['STT_SMJD']),
                          self.input_p_hdu.header['STT_SMJD'])
        assert np.isclose(float(self.p_hdu.header['STT_OFFS']),
                          self.input_p_hdu.header['STT_OFFS'])
        assert self.p_hdu.header['DATE-OBS'].startswith(self.input_p_hdu.header['DATE-OBS'])

    def test_set_freq(self):
        self.p_hdu.frequency = self.input_p_hdu.frequency
        assert (self.p_hdu.header['OBSNCHAN'] ==
                self.input_p_hdu.header['OBSNCHAN'])
        assert (self.p_hdu.header['OBSFREQ'] ==
                self.input_p_hdu.header['OBSFREQ'])
        assert (self.p_hdu.header['OBSBW'] ==
                self.input_p_hdu.header['OBSBW'])

    def test_set_sideband(self):
        self.p_hdu.header['OBSBW'] = self.input_p_hdu.header['OBSBW']
        self.p_hdu.sideband = -self.input_p_hdu.sideband
        assert (self.p_hdu.header['OBSBW'] ==
                -self.input_p_hdu.header['OBSBW'])
        self.p_hdu.sideband = self.input_p_hdu.sideband
        assert (self.p_hdu.header['OBSBW'] ==
                self.input_p_hdu.header['OBSBW'])

    def test_set_mode(self):
        self.p_hdu.obs_mode = 'PSR'
        assert self.p_hdu.header['OBS_MODE'] == 'PSR'
        with pytest.raises(AssertionError):
            self.p_hdu.obs_mode = 'BASEBAND'

    def test_set_skycoord(self):
        self.p_hdu.ra = self.input_p_hdu.ra
        self.p_hdu.dec = self.input_p_hdu.dec
        assert (Longitude(self.p_hdu.header['RA'], unit=u.hourangle) ==
                Longitude(self.input_p_hdu.header['RA'], unit=u.hourangle))
        assert (Latitude(self.p_hdu.header['DEC'], unit=u.deg) ==
                Latitude(self.input_p_hdu.header['DEC'], unit=u.deg))


class TestPSRHDUWriter(TestWriter):
    def setup(self):
        super().setup()
        # add Primary
        self.psr_hdu_no_shape = psrfits.SubintHDU(primary_hdu=self.input_p_hdu)
        self.psr_hdu = psrfits.SubintHDU(primary_hdu=self.input_p_hdu)
        self.psr_hdu.sample_shape = self.reader.sample_shape
        self.psr_hdu._init_columns()
        # Since this test only have one channel, we will not test this setting
        # here.
        self.psr_hdu.header['CHAN_BW'] = self.reader.ih.header['CHAN_BW']

    def test_mode(self):
        assert (self.psr_hdu.mode == 'PSR')
        assert isinstance(self.psr_hdu, psrfits.PSRSubintHDU)

    def test_init_columns(self):
        # The columns are initialied in the setup
        assert self.psr_hdu.data['DATA'].shape == ((self.reader.shape[0],) +
                                                   (self.reader.shape[1:][::-1]))
        # Test no sample shape excpetion
        with pytest.raises(ValueError):
            self.psr_hdu_no_shape._init_columns()

    def test_set_nrow(self):
        assert self.psr_hdu.nbin == self.reader.ih.nbin

    def test_set_nchan(self):
        assert self.psr_hdu.nchan == self.reader.ih.nchan

    def test_set_npol(self):
        assert self.psr_hdu.npol == self.reader.ih.npol

    def test_set_nbin(self):
        assert self.psr_hdu.nbin == self.reader.ih.nbin

    def test_shape(self):
        assert self.psr_hdu.shape == self.reader.ih.shape

    def test_set_start_time(self):
        self.psr_hdu.start_time = self.reader.start_time
        dt = self.psr_hdu.start_time - self.reader.start_time
        assert dt < 1 * u.ns

    def test_set_frequency(self):
        self.psr_hdu.frequency = self.reader.frequency
        assert self.psr_hdu.data['DAT_FREQ'] == self.reader.ih.data['DAT_FREQ']

    def test_data_column_writing(self, tmpdir):
        # Only test setting array here. no real scaling and offseting
        # calculation.
        test_fits = str(tmpdir.join('test_column_writing.fits'))
        test_data = self.reader.read(1)
        # PSRFITS do not truncate data, it arounds them
        in_data = np.around(((test_data - self.reader.ih.data['DAT_OFFS']) /
                            self.reader.ih.data['DAT_SCL']))
        self.psr_hdu.data['DATA'] = in_data.reshape(self.psr_hdu.data['DATA'].shape)
        self.psr_hdu.data['DAT_SCL'] = self.reader.ih.data['DAT_SCL']
        self.psr_hdu.data['DAT_OFFS'] = self.reader.ih.data['DAT_OFFS']
        # Write
        hdul = self.psr_hdu.get_hdu_list()
        hdul.writeto(test_fits)
        column_reader = psrfits.open(test_fits, weighted=False)
        assert np.all(np.isclose(self.reader.ih.data['DATA'],
                                 column_reader.ih.data['DATA']))
        new_in_data = column_reader.read(1)
        assert np.array_equal(test_data, new_in_data)
