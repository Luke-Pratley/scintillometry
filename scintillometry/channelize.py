# Licensed under the GPLv3 - see LICENSE

import operator

import numpy as np

from .base import TaskBase
from .fourier import get_fft_maker


__all__ = ['ChannelizeTask']


class ChannelizeTask(TaskBase):
    """Basic channelizer.

    Divides input into blocks of ``n`` time samples, Fourier transforming each
    block.  The output sample shape is ``(channel,) + ih.sample_shape``.

    Parameters
    ----------
    ih : task or `baseband` stream reader
        Input data stream, with time as the first axis.
    n : int
        Number of input samples to channelize.  For complex input, output will
        have ``n`` channels; for real input, it will have ``n // 2 + 1``.
    samples_per_frame : int, optional
        Number of complete output samples per frame (see Notes).  Default: 1.
    frequency : `~astropy.units.Quantity`, optional
        Frequencies for each channel in ``ih`` (channelized frequencies will
        be calculated).  Default: taken from ``ih`` (if available).
    sideband : array, optional
        Whether frequencies in ``ih`` are upper (+1) or lower (-1) sideband.
        Default: taken from ``ih`` (if available).
    FFT : FFT maker or None, optional
        FFT maker.  Default: `None`, in which case the channelizer uses
        `~scintillometry.fourier.numpy.NumpyFFTMaker`.

    Notes
    -----
    Instances initialize an FFT that acts upon axis 1 of an input with shape::

        (samples_per_frame, n) + ih.sample_shape

    Setting ``samples_per_frame`` to a number larger than 1 results in the FFT
    performing channelization on multiple blocks per call.  Depending on the
    backend used, this may speed up sequential channelization, though for tests
    using `numpy.fft` the performance improvement seems to be negligible.
    """

    def __init__(self, ih, n, samples_per_frame=1,
                 frequency=None, sideband=None, FFT=None):

        n = operator.index(n)
        samples_per_frame = operator.index(samples_per_frame)
        sample_rate = ih.sample_rate / n
        nsample = samples_per_frame * (ih.shape[0] // n // samples_per_frame)
        assert nsample > 0, "not enough samples to fill one frame of data!"

        # Initialize channelizer.
        if FFT is None:
            FFT = get_fft_maker('numpy')

        self._fft = FFT((samples_per_frame, n) + ih.sample_shape,
                        ih.dtype, axis=1, sample_rate=ih.sample_rate)

        super().__init__(ih, shape=(nsample,) + self._fft.frequency_shape[1:],
                         sample_rate=sample_rate,
                         samples_per_frame=samples_per_frame,
                         frequency=frequency, sideband=sideband,
                         dtype=self._fft.frequency_dtype)

        if self._frequency is not None:
            # Do not use in-place, since _frequency is likely broadcast.
            self._frequency = (self._frequency +
                               self._fft.frequency * self.sideband)

    def function(self, data):
        return self._fft(data.reshape(self._fft.time_shape))


class DechannelizeTask(TaskBase):
    """Basic dechannelizer.

    Inverse Fourier transform on first sample axis (which gets removed).

    Parameters
    ----------
    ih : task or `baseband` stream reader
        Input data stream, with time as the first axis, and Fourier channel
        as the second.
    samples_per_frame : int, optional
        Number of complete output samples per frame.  Default: inferred from
        underlying stream, i.e., ``ih.samples_per_frame * ih.shape[1]``.
    frequency : `~astropy.units.Quantity`, optional
        Frequencies for each output channel.  Default: inferred from ``ih``
        (if available).
    sideband : array, optional
        Whether frequencies are upper (+1) or lower (-1) sideband.
        Default: taken from ``ih`` (if available).
    FFT : FFT maker or None, optional
        FFT maker.  Default: `None`, in which case the channelizer uses
        `~scintillometry.fourier.numpy.NumpyFFTMaker`.

    Notes
    -----
    To construct a Dechannelizer for a given Channelizer instance, use
    the ``from_channelizer`` classmethod.

    """

    def __init__(self, ih, n=None, samples_per_frame=None,
                 frequency=None, sideband=None, dtype=None, FFT=None):

        if frequency is None and hasattr(ih, 'frequency'):
            frequency = ih.frequency[0]
        if sideband is None and hasattr(ih, 'sideband'):
            sideband = ih.sideband[0]
        if dtype is None:
            dtype = ih.dtype  # this keeps it complex by default.

        if n is None:
            if dtype.kind == 'c':
                n = ih.sample_shape[0]
            else:
                raise ValueError("Need to pass in explicit n for real transform.")
        sample_rate = ih.sample_rate * n

        # Initialize dechannelizer.
        if FFT is None:
            FFT = get_fft_maker('numpy')

        self._ifft = FFT((ih.samples_per_frame, n) + ih.sample_shape,
                         dtype=dtype, axis=1, direction='inverse')

        super().__init__(ih, shape=(ih.shape[0] * n,) + ih.shape[2:],
                         sample_rate=sample_rate,
                         samples_per_frame=samples_per_frame,
                         frequency=frequency, sideband=sideband,
                         dtype=self._ifft.time_dtype)

    @classmethod
    def from_channelizer(self, ih, channelizer):
        """Create a DechannelizeTask that undoes a ChannelizerTask.

        Paremeters
        ----------
        ih : task or `baseband` stream reader
            Input data stream to be dechannelized.
        channelizer : `~scintillometry.channelize.ChannelizerTask`
            Channelizer that produced the sampling of the input stream.
        """
        # TODO: would be nicer to somehow use _fft.inverse().
        return DechannelizeTask(ih, channelizer._fft.time_shape[1],
                                dtype=channelizer._fft.time_dtype)

    def function(self, data):
        return self._ifft(data).reshape((-1,) + self.sample_shape)
