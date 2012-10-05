# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.protocols.basic}.
"""

from __future__ import division, absolute_import

import struct

from twisted.python.compat import _PY3, iterbytes
from twisted.trial import unittest
from twisted.protocols import basic
from twisted.internet import protocol, error, task
from twisted.test import proto_helpers

_PY3NEWSTYLESKIP = "All classes are new style on Python 3."


class LineTester(basic.LineReceiver):
    """
    A line receiver that parses data received and make actions on some tokens.

    @type delimiter: C{bytes}
    @ivar delimiter: character used between received lines.
    @type MAX_LENGTH: C{int}
    @ivar MAX_LENGTH: size of a line when C{lineLengthExceeded} will be called.
    @type clock: L{twisted.internet.task.Clock}
    @ivar clock: clock simulating reactor callLater. Pass it to constructor if
        you want to use the pause/rawpause functionalities.
    """

    delimiter = b'\n'
    MAX_LENGTH = 64

    def __init__(self, clock=None):
        """
        If given, use a clock to make callLater calls.
        """
        self.clock = clock


    def connectionMade(self):
        """
        Create/clean data received on connection.
        """
        self.received = []


    def lineReceived(self, line):
        """
        Receive line and make some action for some tokens: pause, rawpause,
        stop, len, produce, unproduce.
        """
        self.received.append(line)
        if line == b'':
            self.setRawMode()
        elif line == b'pause':
            self.pauseProducing()
            self.clock.callLater(0, self.resumeProducing)
        elif line == b'rawpause':
            self.pauseProducing()
            self.setRawMode()
            self.received.append(b'')
            self.clock.callLater(0, self.resumeProducing)
        elif line == b'stop':
            self.stopProducing()
        elif line[:4] == b'len ':
            self.length = int(line[4:])
        elif line.startswith(b'produce'):
            self.transport.registerProducer(self, False)
        elif line.startswith(b'unproduce'):
            self.transport.unregisterProducer()


    def rawDataReceived(self, data):
        """
        Read raw data, until the quantity specified by a previous 'len' line is
        reached.
        """
        data, rest = data[:self.length], data[self.length:]
        self.length = self.length - len(data)
        self.received[-1] = self.received[-1] + data
        if self.length == 0:
            self.setLineMode(rest)


    def lineLengthExceeded(self, line):
        """
        Adjust line mode when long lines received.
        """
        if len(line) > self.MAX_LENGTH + 1:
            self.setLineMode(line[self.MAX_LENGTH + 1:])



class LineOnlyTester(basic.LineOnlyReceiver):
    """
    A buffering line only receiver.
    """
    delimiter = b'\n'
    MAX_LENGTH = 64

    def connectionMade(self):
        """
        Create/clean data received on connection.
        """
        self.received = []


    def lineReceived(self, line):
        """
        Save received data.
        """
        self.received.append(line)


class LineReceiverTestCase(unittest.SynchronousTestCase):
    """
    Test LineReceiver, using the C{LineTester} wrapper.
    """
    buffer = b'''\
len 10

0123456789len 5

1234
len 20
foo 123

0123456789
012345678len 0
foo 5

1234567890123456789012345678901234567890123456789012345678901234567890
len 1

a'''

    output = [b'len 10', b'0123456789', b'len 5', b'1234\n',
              b'len 20', b'foo 123', b'0123456789\n012345678',
              b'len 0', b'foo 5', b'', b'67890', b'len 1', b'a']

    def testBuffer(self):
        """
        Test buffering for different packet size, checking received matches
        expected data.
        """
        for packet_size in range(1, 10):
            t = proto_helpers.StringIOWithoutClosing()
            a = LineTester()
            a.makeConnection(protocol.FileWrapper(t))
            for i in range(len(self.buffer) // packet_size + 1):
                s = self.buffer[i*packet_size:(i+1)*packet_size]
                a.dataReceived(s)
            self.assertEqual(self.output, a.received)


    pause_buf = b'twiddle1\ntwiddle2\npause\ntwiddle3\n'

    pause_output1 = [b'twiddle1', b'twiddle2', b'pause']
    pause_output2 = pause_output1+[b'twiddle3']


    def test_pausing(self):
        """
        Test pause inside data receiving. It uses fake clock to see if
        pausing/resuming work.
        """
        for packet_size in range(1, 10):
            t = proto_helpers.StringIOWithoutClosing()
            clock = task.Clock()
            a = LineTester(clock)
            a.makeConnection(protocol.FileWrapper(t))
            for i in range(len(self.pause_buf) // packet_size + 1):
                s = self.pause_buf[i*packet_size:(i+1)*packet_size]
                a.dataReceived(s)
            self.assertEqual(self.pause_output1, a.received)
            clock.advance(0)
            self.assertEqual(self.pause_output2, a.received)

    rawpause_buf = b'twiddle1\ntwiddle2\nlen 5\nrawpause\n12345twiddle3\n'

    rawpause_output1 = [b'twiddle1', b'twiddle2', b'len 5', b'rawpause', b'']
    rawpause_output2 = [b'twiddle1', b'twiddle2', b'len 5', b'rawpause',
                        b'12345', b'twiddle3']


    def test_rawPausing(self):
        """
        Test pause inside raw date receiving.
        """
        for packet_size in range(1, 10):
            t = proto_helpers.StringIOWithoutClosing()
            clock = task.Clock()
            a = LineTester(clock)
            a.makeConnection(protocol.FileWrapper(t))
            for i in range(len(self.rawpause_buf) // packet_size + 1):
                s = self.rawpause_buf[i*packet_size:(i+1)*packet_size]
                a.dataReceived(s)
            self.assertEqual(self.rawpause_output1, a.received)
            clock.advance(0)
            self.assertEqual(self.rawpause_output2, a.received)

    stop_buf = b'twiddle1\ntwiddle2\nstop\nmore\nstuff\n'

    stop_output = [b'twiddle1', b'twiddle2', b'stop']


    def test_stopProducing(self):
        """
        Test stop inside producing.
        """
        for packet_size in range(1, 10):
            t = proto_helpers.StringIOWithoutClosing()
            a = LineTester()
            a.makeConnection(protocol.FileWrapper(t))
            for i in range(len(self.stop_buf) // packet_size + 1):
                s = self.stop_buf[i*packet_size:(i+1)*packet_size]
                a.dataReceived(s)
            self.assertEqual(self.stop_output, a.received)


    def test_lineReceiverAsProducer(self):
        """
        Test produce/unproduce in receiving.
        """
        a = LineTester()
        t = proto_helpers.StringIOWithoutClosing()
        a.makeConnection(protocol.FileWrapper(t))
        a.dataReceived(b'produce\nhello world\nunproduce\ngoodbye\n')
        self.assertEqual(a.received,
                          [b'produce', b'hello world', b'unproduce', b'goodbye'])


    def test_clearLineBuffer(self):
        """
        L{LineReceiver.clearLineBuffer} removes all buffered data and returns
        it as a C{bytes} and can be called from beneath C{dataReceived}.
        """
        class ClearingReceiver(basic.LineReceiver):
            def lineReceived(self, line):
                self.line = line
                self.rest = self.clearLineBuffer()

        protocol = ClearingReceiver()
        protocol.dataReceived(b'foo\r\nbar\r\nbaz')
        self.assertEqual(protocol.line, b'foo')
        self.assertEqual(protocol.rest, b'bar\r\nbaz')

        # Deliver another line to make sure the previously buffered data is
        # really gone.
        protocol.dataReceived(b'quux\r\n')
        self.assertEqual(protocol.line, b'quux')
        self.assertEqual(protocol.rest, b'')



class LineOnlyReceiverTestCase(unittest.SynchronousTestCase):
    """
    Test line only receiveer.
    """
    buffer = b"""foo
    bleakness
    desolation
    plastic forks
    """

    def test_buffer(self):
        """
        Test buffering over line protocol: data received should match buffer.
        """
        t = proto_helpers.StringTransport()
        a = LineOnlyTester()
        a.makeConnection(t)
        for c in iterbytes(self.buffer):
            a.dataReceived(c)
        self.assertEqual(a.received, self.buffer.split(b'\n')[:-1])


    def test_lineTooLong(self):
        """
        Test sending a line too long: it should close the connection.
        """
        t = proto_helpers.StringTransport()
        a = LineOnlyTester()
        a.makeConnection(t)
        res = a.dataReceived(b'x'*200)
        self.assertIsInstance(res, error.ConnectionLost)



class TestMixin:

    def connectionMade(self):
        self.received = []


    def stringReceived(self, s):
        self.received.append(s)

    MAX_LENGTH = 50
    closed = 0


    def connectionLost(self, reason):
        self.closed = 1



class TestNetstring(TestMixin, basic.NetstringReceiver):

    def stringReceived(self, s):
        self.received.append(s)
        self.transport.write(s)



class LPTestCaseMixin:

    illegalStrings = []
    protocol = None


    def getProtocol(self):
        """
        Return a new instance of C{self.protocol} connected to a new instance
        of L{proto_helpers.StringTransport}.
        """
        t = proto_helpers.StringTransport()
        a = self.protocol()
        a.makeConnection(t)
        return a


    def test_illegal(self):
        """
        Assert that illegal strings cause the transport to be closed.
        """
        for s in self.illegalStrings:
            r = self.getProtocol()
            for c in iterbytes(s):
                r.dataReceived(c)
            self.assertTrue(r.transport.disconnecting)



class NetstringReceiverTestCase(unittest.SynchronousTestCase, LPTestCaseMixin):

    strings = [b'hello', b'world', b'how', b'are', b'you123', b':today',
               b"a"*515]

    illegalStrings = [
        b'9999999999999999999999', b'abc', b'4:abcde',
        b'51:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab,',]

    protocol = TestNetstring

    def setUp(self):
        self.transport = proto_helpers.StringTransport()
        self.netstringReceiver = TestNetstring()
        self.netstringReceiver.makeConnection(self.transport)


    def test_buffer(self):
        """
        Strings can be received in chunks of different lengths.
        """
        for packet_size in range(1, 10):
            t = proto_helpers.StringTransport()
            a = TestNetstring()
            a.MAX_LENGTH = 699
            a.makeConnection(t)
            for s in self.strings:
                a.sendString(s)
            out = t.value()
            for i in range(len(out) // packet_size + 1):
                s = out[i*packet_size:(i+1)*packet_size]
                if s:
                    a.dataReceived(s)
            self.assertEqual(a.received, self.strings)


    def test_receiveEmptyNetstring(self):
        """
        Empty netstrings (with length '0') can be received.
        """
        self.netstringReceiver.dataReceived(b"0:,")
        self.assertEqual(self.netstringReceiver.received, [b""])


    def test_receiveOneCharacter(self):
        """
        One-character netstrings can be received.
        """
        self.netstringReceiver.dataReceived(b"1:a,")
        self.assertEqual(self.netstringReceiver.received, [b"a"])


    def test_receiveTwoCharacters(self):
        """
        Two-character netstrings can be received.
        """
        self.netstringReceiver.dataReceived(b"2:ab,")
        self.assertEqual(self.netstringReceiver.received, [b"ab"])


    def test_receiveNestedNetstring(self):
        """
        Netstrings with embedded netstrings. This test makes sure that
        the parser does not become confused about the ',' and ':'
        characters appearing inside the data portion of the netstring.
        """
        self.netstringReceiver.dataReceived(b"4:1:a,,")
        self.assertEqual(self.netstringReceiver.received, [b"1:a,"])


    def test_moreDataThanSpecified(self):
        """
        Netstrings containing more data than expected are refused.
        """
        self.netstringReceiver.dataReceived(b"2:aaa,")
        self.assertTrue(self.transport.disconnecting)


    def test_moreDataThanSpecifiedBorderCase(self):
        """
        Netstrings that should be empty according to their length
        specification are refused if they contain data.
        """
        self.netstringReceiver.dataReceived(b"0:a,")
        self.assertTrue(self.transport.disconnecting)


    def test_missingNumber(self):
        """
        Netstrings without leading digits that specify the length
        are refused.
        """
        self.netstringReceiver.dataReceived(b":aaa,")
        self.assertTrue(self.transport.disconnecting)


    def test_missingColon(self):
        """
        Netstrings without a colon between length specification and
        data are refused.
        """
        self.netstringReceiver.dataReceived(b"3aaa,")
        self.assertTrue(self.transport.disconnecting)


    def test_missingNumberAndColon(self):
        """
        Netstrings that have no leading digits nor a colon are
        refused.
        """
        self.netstringReceiver.dataReceived(b"aaa,")
        self.assertTrue(self.transport.disconnecting)


    def test_onlyData(self):
        """
        Netstrings consisting only of data are refused.
        """
        self.netstringReceiver.dataReceived(b"aaa")
        self.assertTrue(self.transport.disconnecting)


    def test_receiveNetstringPortions_1(self):
        """
        Netstrings can be received in two portions.
        """
        self.netstringReceiver.dataReceived(b"4:aa")
        self.netstringReceiver.dataReceived(b"aa,")
        self.assertEqual(self.netstringReceiver.received, [b"aaaa"])
        self.assertTrue(self.netstringReceiver._payloadComplete())


    def test_receiveNetstringPortions_2(self):
        """
        Netstrings can be received in more than two portions, even if
        the length specification is split across two portions.
        """
        for part in [b"1", b"0:01234", b"56789", b","]:
            self.netstringReceiver.dataReceived(part)
        self.assertEqual(self.netstringReceiver.received, [b"0123456789"])


    def test_receiveNetstringPortions_3(self):
        """
        Netstrings can be received one character at a time.
        """
        for part in [b"2", b":", b"a", b"b", b","]:
            self.netstringReceiver.dataReceived(part)
        self.assertEqual(self.netstringReceiver.received, [b"ab"])


    def test_receiveTwoNetstrings(self):
        """
        A stream of two netstrings can be received in two portions,
        where the first portion contains the complete first netstring
        and the length specification of the second netstring.
        """
        self.netstringReceiver.dataReceived(b"1:a,1")
        self.assertTrue(self.netstringReceiver._payloadComplete())
        self.assertEqual(self.netstringReceiver.received, [b"a"])
        self.netstringReceiver.dataReceived(b":b,")
        self.assertEqual(self.netstringReceiver.received, [b"a", b"b"])


    def test_maxReceiveLimit(self):
        """
        Netstrings with a length specification exceeding the specified
        C{MAX_LENGTH} are refused.
        """
        tooLong = self.netstringReceiver.MAX_LENGTH + 1
        self.netstringReceiver.dataReceived(b"".join(
                (bytes(tooLong), b":", b"a" * tooLong)))
        self.assertTrue(self.transport.disconnecting)


    def test_consumeLength(self):
        """
        C{_consumeLength} returns the expected length of the
        netstring, including the trailing comma.
        """
        self.netstringReceiver._remainingData = b"12:"
        self.netstringReceiver._consumeLength()
        self.assertEqual(self.netstringReceiver._expectedPayloadSize, 13)


    def test_consumeLengthBorderCase1(self):
        """
        C{_consumeLength} works as expected if the length specification
        contains the value of C{MAX_LENGTH} (border case).
        """
        self.netstringReceiver._remainingData = b"12:"
        self.netstringReceiver.MAX_LENGTH = 12
        self.netstringReceiver._consumeLength()
        self.assertEqual(self.netstringReceiver._expectedPayloadSize, 13)


    def test_consumeLengthBorderCase2(self):
        """
        C{_consumeLength} raises a L{basic.NetstringParseError} if
        the length specification exceeds the value of C{MAX_LENGTH}
        by 1 (border case).
        """
        self.netstringReceiver._remainingData = b"12:"
        self.netstringReceiver.MAX_LENGTH = 11
        self.assertRaises(basic.NetstringParseError,
                          self.netstringReceiver._consumeLength)


    def test_consumeLengthBorderCase3(self):
        """
        C{_consumeLength} raises a L{basic.NetstringParseError} if
        the length specification exceeds the value of C{MAX_LENGTH}
        by more than 1.
        """
        self.netstringReceiver._remainingData = b"1000:"
        self.netstringReceiver.MAX_LENGTH = 11
        self.assertRaises(basic.NetstringParseError,
                          self.netstringReceiver._consumeLength)


    def test_deprecatedModuleAttributes(self):
        """
        Accessing one of the old module attributes used by the
        NetstringReceiver parser emits a deprecation warning.
        """
        basic.LENGTH, basic.DATA, basic.COMMA, basic.NUMBER
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_deprecatedModuleAttributes])

        self.assertEqual(len(warnings), 4)
        for warning in warnings:
            self.assertEqual(warning['category'], DeprecationWarning)
        self.assertEqual(
            warnings[0]['message'],
            ("twisted.protocols.basic.LENGTH was deprecated in Twisted 10.2.0: "
             "NetstringReceiver parser state is private."))
        self.assertEqual(
            warnings[1]['message'],
            ("twisted.protocols.basic.DATA was deprecated in Twisted 10.2.0: "
             "NetstringReceiver parser state is private."))
        self.assertEqual(
            warnings[2]['message'],
            ("twisted.protocols.basic.COMMA was deprecated in Twisted 10.2.0: "
             "NetstringReceiver parser state is private."))
        self.assertEqual(
            warnings[3]['message'],
            ("twisted.protocols.basic.NUMBER was deprecated in Twisted 10.2.0: "
             "NetstringReceiver parser state is private."))



class IntNTestCaseMixin(LPTestCaseMixin):
    """
    TestCase mixin for int-prefixed protocols.
    """

    protocol = None
    strings = None
    illegalStrings = None
    partialStrings = None

    def test_receive(self):
        """
        Test receiving data find the same data send.
        """
        r = self.getProtocol()
        for s in self.strings:
            for c in iterbytes(struct.pack(r.structFormat,len(s)) + s):
                r.dataReceived(c)
        self.assertEqual(r.received, self.strings)


    def test_partial(self):
        """
        Send partial data, nothing should be definitely received.
        """
        for s in self.partialStrings:
            r = self.getProtocol()
            for c in iterbytes(s):
                r.dataReceived(c)
            self.assertEqual(r.received, [])


    def test_send(self):
        """
        Test sending data over protocol.
        """
        r = self.getProtocol()
        r.sendString(b"b" * 16)
        self.assertEqual(r.transport.value(),
            struct.pack(r.structFormat, 16) + b"b" * 16)


    def test_lengthLimitExceeded(self):
        """
        When a length prefix is received which is greater than the protocol's
        C{MAX_LENGTH} attribute, the C{lengthLimitExceeded} method is called
        with the received length prefix.
        """
        length = []
        r = self.getProtocol()
        r.lengthLimitExceeded = length.append
        r.MAX_LENGTH = 10
        r.dataReceived(struct.pack(r.structFormat, 11))
        self.assertEqual(length, [11])


    def test_longStringNotDelivered(self):
        """
        If a length prefix for a string longer than C{MAX_LENGTH} is delivered
        to C{dataReceived} at the same time as the entire string, the string is
        not passed to C{stringReceived}.
        """
        r = self.getProtocol()
        r.MAX_LENGTH = 10
        r.dataReceived(
            struct.pack(r.structFormat, 11) + b'x' * 11)
        self.assertEqual(r.received, [])



class RecvdAttributeMixin(object):
    """
    Mixin defining tests for string receiving protocols with a C{recvd}
    attribute which should be settable by application code, to be combined with
    L{IntNTestCaseMixin} on a L{TestCase} subclass
    """

    def makeMessage(self, protocol, data):
        """
        Return C{data} prefixed with message length in C{protocol.structFormat}
        form.
        """
        return struct.pack(protocol.structFormat, len(data)) + data


    def test_recvdContainsRemainingData(self):
        """
        In stringReceived, recvd contains the remaining data that was passed to
        dataReceived that was not part of the current message.
        """
        result = []
        r = self.getProtocol()
        def stringReceived(receivedString):
            result.append(r.recvd)
        r.stringReceived = stringReceived
        completeMessage = (struct.pack(r.structFormat, 5) + (b'a' * 5))
        incompleteMessage = (struct.pack(r.structFormat, 5) + (b'b' * 4))
        # Receive a complete message, followed by an incomplete one
        r.dataReceived(completeMessage + incompleteMessage)
        self.assertEquals(result, [incompleteMessage])


    def test_recvdChanged(self):
        """
        In stringReceived, if recvd is changed, messages should be parsed from
        it rather than the input to dataReceived.
        """
        r = self.getProtocol()
        result = []
        payloadC = b'c' * 5
        messageC = self.makeMessage(r, payloadC)
        def stringReceived(receivedString):
            if not result:
                r.recvd = messageC
            result.append(receivedString)
        r.stringReceived = stringReceived
        payloadA = b'a' * 5
        payloadB = b'b' * 5
        messageA = self.makeMessage(r, payloadA)
        messageB = self.makeMessage(r, payloadB)
        r.dataReceived(messageA + messageB)
        self.assertEquals(result, [payloadA, payloadC])


    def test_switching(self):
        """
        Data already parsed by L{IntNStringReceiver.dataReceived} is not
        reparsed if C{stringReceived} consumes some of the
        L{IntNStringReceiver.recvd} buffer.
        """
        proto = self.getProtocol()
        mix = []
        SWITCH = b"\x00\x00\x00\x00"
        for s in self.strings:
            mix.append(self.makeMessage(proto, s))
            mix.append(SWITCH)

        result = []
        def stringReceived(receivedString):
            result.append(receivedString)
            proto.recvd = proto.recvd[len(SWITCH):]

        proto.stringReceived = stringReceived
        proto.dataReceived(b"".join(mix))
        # Just another byte, to trigger processing of anything that might have
        # been left in the buffer (should be nothing).
        proto.dataReceived(b"\x01")
        self.assertEqual(result, self.strings)
        # And verify that another way
        self.assertEqual(proto.recvd, b"\x01")


    def test_recvdInLengthLimitExceeded(self):
        """
        The L{IntNStringReceiver.recvd} buffer contains all data not yet
        processed by L{IntNStringReceiver.dataReceived} if the
        C{lengthLimitExceeded} event occurs.
        """
        proto = self.getProtocol()
        DATA = b"too long"
        proto.MAX_LENGTH = len(DATA) - 1
        message = self.makeMessage(proto, DATA)

        result = []
        def lengthLimitExceeded(length):
            result.append(length)
            result.append(proto.recvd)

        proto.lengthLimitExceeded = lengthLimitExceeded
        proto.dataReceived(message)
        self.assertEqual(result[0], len(DATA))
        self.assertEqual(result[1], message)



class TestInt32(TestMixin, basic.Int32StringReceiver):
    """
    A L{basic.Int32StringReceiver} storing received strings in an array.

    @ivar received: array holding received strings.
    """



class Int32TestCase(unittest.SynchronousTestCase, IntNTestCaseMixin, RecvdAttributeMixin):
    """
    Test case for int32-prefixed protocol
    """
    protocol = TestInt32
    strings = [b"a", b"b" * 16]
    illegalStrings = [b"\x10\x00\x00\x00aaaaaa"]
    partialStrings = [b"\x00\x00\x00", b"hello there", b""]

    def test_data(self):
        """
        Test specific behavior of the 32-bits length.
        """
        r = self.getProtocol()
        r.sendString(b"foo")
        self.assertEqual(r.transport.value(), b"\x00\x00\x00\x03foo")
        r.dataReceived(b"\x00\x00\x00\x04ubar")
        self.assertEqual(r.received, [b"ubar"])



class TestInt16(TestMixin, basic.Int16StringReceiver):
    """
    A L{basic.Int16StringReceiver} storing received strings in an array.

    @ivar received: array holding received strings.
    """



class Int16TestCase(unittest.SynchronousTestCase, IntNTestCaseMixin, RecvdAttributeMixin):
    """
    Test case for int16-prefixed protocol
    """
    protocol = TestInt16
    strings = [b"a", b"b" * 16]
    illegalStrings = [b"\x10\x00aaaaaa"]
    partialStrings = [b"\x00", b"hello there", b""]

    def test_data(self):
        """
        Test specific behavior of the 16-bits length.
        """
        r = self.getProtocol()
        r.sendString(b"foo")
        self.assertEqual(r.transport.value(), b"\x00\x03foo")
        r.dataReceived(b"\x00\x04ubar")
        self.assertEqual(r.received, [b"ubar"])


    def test_tooLongSend(self):
        """
        Send too much data: that should cause an error.
        """
        r = self.getProtocol()
        tooSend = b"b" * (2**(r.prefixLength*8) + 1)
        self.assertRaises(AssertionError, r.sendString, tooSend)



class NewStyleTestInt16(TestInt16, object):
    """
    A new-style class version of TestInt16
    """



class NewStyleInt16TestCase(Int16TestCase):
    """
    This test case verifies that IntNStringReceiver still works when inherited
    by a new-style class.
    """
    if _PY3:
        skip = _PY3NEWSTYLESKIP

    protocol = NewStyleTestInt16



class TestInt8(TestMixin, basic.Int8StringReceiver):
    """
    A L{basic.Int8StringReceiver} storing received strings in an array.

    @ivar received: array holding received strings.
    """



class Int8TestCase(unittest.SynchronousTestCase, IntNTestCaseMixin, RecvdAttributeMixin):
    """
    Test case for int8-prefixed protocol
    """
    protocol = TestInt8
    strings = [b"a", b"b" * 16]
    illegalStrings = [b"\x00\x00aaaaaa"]
    partialStrings = [b"\x08", b"dzadz", b""]


    def test_data(self):
        """
        Test specific behavior of the 8-bits length.
        """
        r = self.getProtocol()
        r.sendString(b"foo")
        self.assertEqual(r.transport.value(), b"\x03foo")
        r.dataReceived(b"\x04ubar")
        self.assertEqual(r.received, [b"ubar"])


    def test_tooLongSend(self):
        """
        Send too much data: that should cause an error.
        """
        r = self.getProtocol()
        tooSend = b"b" * (2**(r.prefixLength*8) + 1)
        self.assertRaises(AssertionError, r.sendString, tooSend)



class OnlyProducerTransport(object):
    # Transport which isn't really a transport, just looks like one to
    # someone not looking very hard.

    paused = False
    disconnecting = False

    def __init__(self):
        self.data = []


    def pauseProducing(self):
        self.paused = True


    def resumeProducing(self):
        self.paused = False


    def write(self, bytes):
        self.data.append(bytes)



class ConsumingProtocol(basic.LineReceiver):
    # Protocol that really, really doesn't want any more bytes.

    def lineReceived(self, line):
        self.transport.write(line)
        self.pauseProducing()



class ProducerTestCase(unittest.SynchronousTestCase):

    def testPauseResume(self):
        p = ConsumingProtocol()
        t = OnlyProducerTransport()
        p.makeConnection(t)

        p.dataReceived(b'hello, ')
        self.failIf(t.data)
        self.failIf(t.paused)
        self.failIf(p.paused)

        p.dataReceived(b'world\r\n')

        self.assertEqual(t.data, [b'hello, world'])
        self.failUnless(t.paused)
        self.failUnless(p.paused)

        p.resumeProducing()

        self.failIf(t.paused)
        self.failIf(p.paused)

        p.dataReceived(b'hello\r\nworld\r\n')

        self.assertEqual(t.data, [b'hello, world', b'hello'])
        self.failUnless(t.paused)
        self.failUnless(p.paused)

        p.resumeProducing()
        p.dataReceived(b'goodbye\r\n')

        self.assertEqual(t.data, [b'hello, world', b'hello', b'world'])
        self.failUnless(t.paused)
        self.failUnless(p.paused)

        p.resumeProducing()

        self.assertEqual(t.data, [b'hello, world', b'hello', b'world', b'goodbye'])
        self.failUnless(t.paused)
        self.failUnless(p.paused)

        p.resumeProducing()

        self.assertEqual(t.data, [b'hello, world', b'hello', b'world', b'goodbye'])
        self.failIf(t.paused)
        self.failIf(p.paused)