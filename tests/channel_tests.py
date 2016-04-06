__author__ = 'eandersson'

import logging

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from pamqp import specification
from pamqp.body import ContentBody
from pamqp.header import ContentHeader

import amqpstorm
from amqpstorm import exception
from amqpstorm import Message
from amqpstorm import Channel
from amqpstorm.exception import *

from tests.utility import FakeConnection
from tests.utility import FakeFrame

logging.basicConfig(level=logging.DEBUG)


class BasicChannelTests(unittest.TestCase):
    def test_channel_build_message(self):
        channel = Channel(0, None, 360)

        message = b'Hello World!'
        message_len = len(message)

        deliver = specification.Basic.Deliver()
        header = ContentHeader(body_size=message_len)
        body = ContentBody(value=message)

        channel._inbound = [deliver, header, body]
        result = channel._build_message()

        self.assertEqual(result._body, message)

    def test_channel_build_out_of_order_message(self):
        channel = Channel(0, None, 360)

        message = b'Hello World!'
        message_len = len(message)

        deliver = specification.Basic.Deliver()
        header = ContentHeader(body_size=message_len)
        body = ContentBody(value=message)

        channel._inbound = [deliver, deliver, header, body]
        result = channel._build_message()

        self.assertEqual(result, None)

    def test_channel_build_message_body(self):
        channel = Channel(0, None, 360)

        message = b'Hello World!'
        message_len = len(message)

        body = ContentBody(value=message)
        channel._inbound = [body]
        result = channel._build_message_body(message_len)

        self.assertEqual(message, result)

    def test_channel_build_empty_inbound_messages(self):
        channel = Channel(0, FakeConnection(), 360)
        channel.set_state(Channel.OPEN)
        result = None
        for message in channel.build_inbound_messages(break_on_empty=True):
            result = message

        self.assertIsNone(result)

    def test_channel_build_inbound_messages(self):
        channel = Channel(0, FakeConnection(), 360)
        channel.set_state(Channel.OPEN)

        message = b'Hello World!'
        message_len = len(message)

        deliver = specification.Basic.Deliver()
        header = ContentHeader(body_size=message_len)
        body = ContentBody(value=message)

        channel._inbound = [deliver, header, body]

        for message in channel.build_inbound_messages(break_on_empty=True):
            self.assertIsInstance(message, Message)

    def test_channel_build_multiple_inbound_messages(self):
        channel = Channel(0, FakeConnection(), 360)
        channel.set_state(Channel.OPEN)

        message = b'Hello World!'
        message_len = len(message)

        deliver = specification.Basic.Deliver()
        header = ContentHeader(body_size=message_len)
        body = ContentBody(value=message)

        channel._inbound = [deliver, header, body, deliver, header, body,
                            deliver, header, body, deliver, header, body]

        index = 0
        for message in channel.build_inbound_messages(break_on_empty=True):
            self.assertIsInstance(message, Message)
            index += 1

        self.assertEqual(index, 4)

    def test_channel_close(self):
        channel = Channel(0, None, 360)

        # Set up Fake Channel.
        channel._inbound = [1, 2, 3]
        channel.set_state(channel.OPEN)
        channel._consumer_tags = [1, 2, 3]

        # Close Channel.
        channel._close_channel(specification.Channel.Close(reply_text=''))

        self.assertEqual(channel._inbound, [])
        self.assertEqual(channel._consumer_tags, [])
        self.assertEqual(channel._state, channel.CLOSED)

    def test_channel_throw_exception_check_for_error(self):
        channel = Channel(0, FakeConnection(), 360)
        channel.set_state(channel.OPEN)
        channel.exceptions.append(AMQPConnectionError('Test'))

        self.assertRaises(AMQPConnectionError, channel.check_for_errors)

    def test_channel_check_error_no_exception(self):
        channel = Channel(0, FakeConnection(), 360)
        channel.set_state(Channel.OPEN)
        channel.check_for_errors()

    def test_channel_check_error_when_closed(self):
        channel = Channel(0, FakeConnection(), 360)

        self.assertRaises(exception.AMQPChannelError, channel.check_for_errors)

    def test_channel_check_error_connection_closed(self):
        channel = Channel(0, FakeConnection(FakeConnection.CLOSED), 360)

        self.assertRaises(exception.AMQPConnectionError,
                          channel.check_for_errors)

    def test_channel_raises_when_closed(self):
        channel = Channel(0, FakeConnection(FakeConnection.OPEN), 360)
        channel.set_state(channel.CLOSED)

        self.assertFalse(channel.is_open)
        self.assertRaisesRegexp(exception.AMQPChannelError,
                                'channel was closed',
                                channel.check_for_errors)
        self.assertTrue(channel.is_closed)

    def test_channel_closed_after_connection_closed(self):
        channel = Channel(0, FakeConnection(FakeConnection.CLOSED), 360)
        channel.set_state(channel.OPEN)

        self.assertTrue(channel.is_open)
        self.assertRaisesRegexp(exception.AMQPConnectionError,
                                'connection was closed',
                                channel.check_for_errors)
        self.assertTrue(channel.is_closed)

    def test_channel_closed_after_connection_exception(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        channel = Channel(0, connection, 360)
        connection.exceptions.append(AMQPConnectionError('error'))
        channel.set_state(channel.OPEN)

        self.assertTrue(connection.is_closed)
        self.assertTrue(channel.is_open)
        self.assertRaisesRegexp(exception.AMQPConnectionError, 'error',
                                channel.check_for_errors)
        self.assertTrue(channel.is_closed)

    def test_channel_consume_exception_when_recoverable(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        connection.set_state(connection.OPEN)
        channel = Channel(0, connection, 360)
        channel.set_state(channel.OPEN)
        channel.exceptions.append(AMQPChannelError('no-route'))

        self.assertTrue(connection.is_open)
        self.assertTrue(channel.is_open)

        self.assertRaisesRegexp(exception.AMQPChannelError, 'no-route',
                                channel.check_for_errors)

        self.assertTrue(channel.is_open)

        channel.check_for_errors()


class ChannelFrameTests(unittest.TestCase):
    def test_channel_unhandled_frame(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        channel = Channel(0, connection, rpc_timeout=360)

        channel.on_frame(FakeFrame())

    def test_channel_basic_cancel_frame(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        channel = Channel(0, connection, rpc_timeout=360)

        channel.on_frame(specification.Basic.Cancel())

    def test_channel_basic_return_frame(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        channel = Channel(0, connection, rpc_timeout=360)

        channel.on_frame(specification.Basic.Return(reply_code=500,
                                                    reply_text='test',
                                                    exchange='exchange',
                                                    routing_key='routing_key'))

        self.assertEqual(str(channel.exceptions[0]),
                         "Message not delivered: test (500) to queue "
                         "'routing_key' from exchange 'exchange'")

    def test_channel_close_frame(self):
        connection = amqpstorm.Connection('localhost', 'guest', 'guest',
                                          lazy=True)
        channel = Channel(0, connection, rpc_timeout=360)

        channel.on_frame(specification.Channel.Close(reply_code=500,
                                                     reply_text='test'))

        self.assertEqual(str(channel.exceptions[0]),
                         'Channel 0 was closed by remote server: test')

    def test_channel_basic_return_raises_when_500(self):
        channel = Channel(0, None, 360)

        basic_return = specification.Basic.Return(reply_code=500,
                                                  reply_text='Error')
        channel._basic_return(basic_return)

        self.assertEqual(len(channel.exceptions), 1)
        why = channel.exceptions.pop(0)
        self.assertIsInstance(why, AMQPMessageError)
        self.assertEqual(str(why), "Message not delivered: Error (500) "
                                   "to queue '' from exchange ''")
