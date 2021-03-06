import unittest
import logging
import sys
sys.path.append('../')
from backend.audio import Audio
from backend.bcm2835audiodriver import Bcm2835AudioDriver
from cleep.exception import InvalidParameter, MissingParameter, CommandError, Unauthorized
from cleep.libs.tests import session, lib
import os
import time
from mock import Mock, MagicMock, patch

class TestAudio(unittest.TestCase):

    def setUp(self):
        self.session = session.TestSession(self)
        logging.basicConfig(level=logging.FATAL, format=u'%(asctime)s %(name)s:%(lineno)d %(levelname)s : %(message)s')

    def tearDown(self):
        self.session.clean()

    def init_session(self, bootstrap={}):
        # force cleep_filesystem
        if 'cleep_filesystem' not in bootstrap:
            cleep_filesystem = MagicMock()
            cleep_filesystem.open.return_value.read.return_value = 'dtparam=audio=on'
            bootstrap['cleep_filesystem'] = cleep_filesystem

        self.module = self.session.setup(Audio, bootstrap=bootstrap)
        self.session.start_module(self.module)

    def test_init(self):
        self.init_session()
        self.assertIsNotNone(self.module.bcm2835_driver)
        self.assertTrue(isinstance(self.module.bcm2835_driver, Bcm2835AudioDriver))

    @patch('backend.audio.Tools')
    def test_init_no_audio_on_device(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': False}
        drivers_mock = Mock()
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })

        self.assertFalse(drivers_mock.get_drivers.called)

    def test_init_configured_driver_not_available(self):
        default_driver = Mock()
        default_driver.is_installed.return_value = False
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [None, default_driver]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })

    def test_init_driver_disabled(self):
        default_driver = Mock()
        default_driver.is_installed.return_value = True
        default_driver.is_enabled.return_value = False
        default_driver.enable.return_value = False
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [None, default_driver]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })

    def test_init_no_driver_available(self):
        default_driver = Mock()
        default_driver.is_installed.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.return_value = None
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })

    def test_get_module_config(self):
        self.init_session()
        conf = self.module.get_module_config()
        logging.debug('Conf: %s' % conf)

        self.assertTrue('devices' in conf)
        self.assertTrue('playback' in conf['devices'])
        self.assertTrue('capture' in conf['devices'])
        self.assertTrue('volumes' in conf)
        self.assertTrue('playback' in conf['volumes'])
        self.assertTrue('capture' in conf['volumes'])
        
        self.assertEqual(conf['devices']['playback'][0]['label'], 'Raspberry pi soundcard')
        # breaks tests during CI (no audio)
        # self.assertEqual(conf['devices']['playback'][0]['enabled'], True)
        # self.assertEqual(conf['devices']['playback'][0]['installed'], True)
        # self.assertEqual(conf['devices']['playback'][0]['device']['deviceid'], 0)
        # self.assertEqual(conf['devices']['playback'][0]['device']['playback'], True)
        # self.assertTrue(conf['devices']['playback'][0]['device']['cardname'].startswith('bcm2835'))
        # self.assertEqual(conf['devices']['playback'][0]['device']['capture'], False)
        # self.assertEqual(conf['devices']['playback'][0]['device']['cardid'], 0)

        # self.assertTrue(isinstance(conf['volumes']['playback'], int))
        # self.assertIsNone(conf['volumes']['capture'])

    @patch('backend.audio.Tools')
    def test_select_device(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': True}
        old_driver = Mock(name='olddriver')
        old_driver.is_installed.return_value = True
        old_driver.disable.return_value = True
        new_driver = Mock(name='newdriver')
        # add mock class variable
        attrs = {'name': 'dummydriver'}
        new_driver.configure_mock(**attrs)
        new_driver.is_installed.return_value = True
        new_driver.enable.return_value = True
        new_driver.is_card_enabled.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [old_driver, old_driver, new_driver]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='selecteddriver')
        self.module._set_config_field = Mock()

        self.module.select_device('dummydriver')
        self.assertTrue(old_driver.disable.called)
        self.assertTrue(new_driver.enable.called)
        self.module._set_config_field.assert_called_with('driver', 'dummydriver')

    @patch('backend.audio.Tools')
    def test_select_device_fallback_old_driver_if_error(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': True}
        old_driver = Mock()
        old_driver.is_installed.return_value = True
        old_driver.disable.return_value = True
        new_driver = Mock()
        # add mock class variable
        attrs = {'name': 'dummydriver'}
        new_driver.configure_mock(**attrs)
        new_driver.is_installed.return_value = True
        new_driver.enable.return_value = False
        new_driver.is_card_enabled.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [old_driver, old_driver, new_driver]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='selecteddriver')
        self.module._set_config_field = Mock()

        with self.assertRaises(CommandError) as cm:
            self.module.select_device('dummydriver')
        self.assertEqual(str(cm.exception), 'Unable to enable selected device')

    def test_select_device_invalid_parameters(self):
        self.init_session()

        with self.assertRaises(MissingParameter) as cm:
            self.module.select_device(None)
        self.assertEqual(str(cm.exception), 'Parameter "driver_name" is missing')
        with self.assertRaises(InvalidParameter) as cm:
            self.module.select_device('')
        self.assertEqual(str(cm.exception), 'Parameter "driver_name" is invalid (specified="")')

    @patch('backend.audio.Tools')
    def test_select_device_unknown_new_driver(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': True}
        old_driver = Mock()
        old_driver.is_installed.return_value = True
        old_driver.disable.return_value = True
        new_driver = Mock()
        # add mock class variable
        attrs = {'name': 'dummydriver'}
        new_driver.configure_mock(**attrs)
        new_driver.is_installed.return_value = True
        new_driver.enable.return_value = True
        new_driver.is_card_enabled.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [old_driver, old_driver, None]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='selecteddriver')
        self.module._set_config_field = Mock()

        with self.assertRaises(InvalidParameter) as cm:
            self.module.select_device('dummydriver')
        self.assertEqual(str(cm.exception), 'Specified driver does not exist')

    @patch('backend.audio.Tools')
    def test_select_device_new_driver_not_installed(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': True}
        old_driver = Mock(name='olddriver')
        old_driver.is_installed.return_value = True
        old_driver.disable.return_value = True
        new_driver = Mock(name='newdriver')
        # add mock class variable
        attrs = {'name': 'dummydriver'}
        new_driver.configure_mock(**attrs)
        new_driver.is_installed.return_value = False
        new_driver.enable.return_value = True
        new_driver.is_card_enabled.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.side_effect = [old_driver, old_driver, new_driver]
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='drivername')
        self.module._set_config_field = Mock()

        with self.assertRaises(InvalidParameter) as cm:
            self.module.select_device('dummydriver')
        self.assertEqual(str(cm.exception), 'Can\'t selected device because its driver seems not to be installed')

    def test_set_volumes(self):
        driver = Mock()
        driver.is_installed.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.return_value = driver
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='dummydriver')

        self.module.set_volumes(12, 34)

        driver.set_volumes.assert_called_with(12, 34)

    @patch('backend.audio.Tools')
    def test_set_volumes_invalid_parameters(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = {'audio': True}
        old_driver = Mock()
        old_driver.is_installed.return_value = True
        old_driver.disable.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.return_value = old_driver
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='selecteddriver')
        self.init_session()

        with self.assertRaises(MissingParameter) as cm:
            self.module.set_volumes(None, 12)
        self.assertEqual(str(cm.exception), 'Parameter "volume" is missing')
        with self.assertRaises(InvalidParameter) as cm:
            self.module.set_volumes(12, '12')
        self.assertEqual(str(cm.exception), 'Parameter "capture" must be of type "int"')
        with self.assertRaises(InvalidParameter) as cm:
            self.module.set_volumes(-12, 12)
        self.assertEqual(str(cm.exception), 'Parameter "playback" must be 0<=playback<=100')
        with self.assertRaises(InvalidParameter) as cm:
            self.module.set_volumes(12, 102)
        self.assertEqual(str(cm.exception), 'Parameter "capture" must be 0<=capture<=100')

    def test_set_volumes_no_driver_selected(self):
        driver = Mock()
        driver.is_installed.return_value = True
        drivers_mock = Mock()
        drivers_mock.get_driver.return_value = None
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value=None)

        volumes = self.module.set_volumes(12, 34)
        logging.debug('Volumes: %s' % volumes)

        self.assertEqual(volumes, { 'playback': None, 'capture': None })
        self.assertFalse(driver.set_volumes.called)

    def test_set_volumes_no_driver_found(self):
        drivers_mock = Mock()
        drivers_mock.get_driver.return_value = None
        self.init_session(bootstrap={
            'drivers': drivers_mock,
        })
        self.module._get_config_field = Mock(return_value='dummydriver')

        volumes = self.module.set_volumes(12, 34)
        logging.debug('Volumes: %s' % volumes)

        self.assertEqual(volumes, { 'playback': None, 'capture': None })

    @patch('backend.audio.Alsa')
    def test_test_playing(self, mock_alsa):
        self.init_session()
        self.module.test_playing()

        time.sleep(1.0)
        self.assertTrue(mock_alsa.return_value.play_sound.called)

    @patch('backend.audio.Alsa')
    def test_test_playing_failed(self, mock_alsa):
        mock_alsa.return_value.play_sound.return_value = False
        self.init_session()
        self.module.test_playing()

        time.sleep(1.0)
        self.assertTrue(mock_alsa.return_value.play_sound.called)

    @patch('backend.audio.Alsa')
    def test_test_recording(self, mock_alsa):
        self.init_session()
        self.module.test_recording()

        self.assertTrue(mock_alsa.return_value.record_sound.called)

    @patch('backend.audio.Alsa')
    def test_test_recording_failed(self, mock_alsa):
        mock_alsa.return_value.play_sound.return_value = False
        self.init_session()
        self.module.test_recording()

        self.assertTrue(mock_alsa.return_value.record_sound.called)

    def test_resource_acquired(self):
        self.init_session()
        self.module._resource_acquired('dummy.resource')





class TestBcm2835AudioDriver(unittest.TestCase):
    def setUp(self):
        self.session = lib.TestLib()
        logging.basicConfig(level=logging.CRITICAL, format=u'%(asctime)s %(name)s:%(lineno)d %(levelname)s : %(message)s')

    def tearDown(self):
        pass

    def init_session(self):
        self.fs = Mock()
        self.driver = Bcm2835AudioDriver()
        self.driver.cleep_filesystem = Mock()
        self.driver._on_registered()

    @patch('backend.bcm2835audiodriver.Tools')
    @patch('backend.bcm2835audiodriver.ConfigTxt')
    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_install(self, mock_asound, mock_configtxt, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': True }
        self.init_session()
        self.driver._install()
        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_configtxt.return_value.enable_audio.called)

    @patch('backend.bcm2835audiodriver.Tools')
    @patch('backend.bcm2835audiodriver.ConfigTxt')
    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_install_enable_audio_failed(self, mock_asound, mock_configtxt, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': True }
        mock_configtxt.return_value.enable_audio.return_value = False
        self.init_session()

        with self.assertRaises(Exception) as cm:
            self.driver._install()
        self.assertEqual(str(cm.exception), 'Error enabling raspberry pi audio')
        self.assertTrue(mock_asound.return_value.delete.called)

    @patch('backend.bcm2835audiodriver.Tools')
    def test_install_with_no_audio_supported(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': False }
        self.init_session()

        with self.assertRaises(Exception) as cm:
            self.driver._install()
        self.assertEqual(str(cm.exception), 'Raspberry pi has no onboard audio device')

    @patch('backend.bcm2835audiodriver.Tools')
    @patch('backend.bcm2835audiodriver.ConfigTxt')
    def test_uninstall(self, mock_configtxt, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': True }
        self.init_session()
        self.driver._uninstall()
        self.assertTrue(mock_configtxt.return_value.disable_audio.called)

    @patch('backend.bcm2835audiodriver.Tools')
    @patch('backend.bcm2835audiodriver.ConfigTxt')
    def test_uninstall_disable_audio_failed(self, mock_configtxt, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': True }
        mock_configtxt.return_value.disable_audio.return_value = False
        self.init_session()

        with self.assertRaises(Exception) as cm:
            self.driver._uninstall()
        self.assertEqual(str(cm.exception), 'Error disabling raspberry pi audio')
        
    @patch('backend.bcm2835audiodriver.Tools')
    def test_uninstall_with_no_audio_supported(self, mock_tools):
        mock_tools.raspberry_pi_infos.return_value = { 'audio': False }
        self.init_session()

        with self.assertRaises(Exception) as cm:
            self.driver._uninstall()
        self.assertEqual(str(cm.exception), 'Raspberry pi has no onboard audio device')

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_enable(self, mock_asound):
        self.init_session()
        mock_alsa = MagicMock()
        self.driver.alsa = mock_alsa
        self.driver.get_cardid_deviceid = Mock(return_value=(0, 0))
        self.driver.get_control_numid = Mock(return_value=1)
    
        self.assertTrue(self.driver.enable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_asound.return_value.save_default_file.called)
        self.assertTrue(mock_alsa.amixer_control.called)
        self.assertTrue(mock_alsa.save.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    @patch('backend.bcm2835audiodriver.Alsa')
    def test_enable_no_card_infos(self, mock_alsa, mock_asound):
        self.init_session()
        self.driver.get_cardid_deviceid = Mock(return_value=(None, None))
    
        self.assertFalse(self.driver.enable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertFalse(mock_asound.return_value.save_default_file.called)
        self.assertFalse(mock_alsa.return_value.amixer_control.called)
        self.assertFalse(mock_alsa.return_value.save.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    @patch('backend.bcm2835audiodriver.Alsa')
    def test_enable_alsa_save_default_file_failed(self, mock_alsa, mock_asound):
        mock_asound.return_value.save_default_file.return_value = False
        self.init_session()
        self.driver.get_cardid_deviceid = Mock(return_value=(0, 0))
    
        self.assertFalse(self.driver.enable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_asound.return_value.save_default_file.called)
        self.assertFalse(mock_alsa.return_value.amixer_control.called)
        self.assertFalse(mock_alsa.return_value.save.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_enable_alsa_amixer_control_failed(self, mock_asound):
        self.init_session()
        mock_alsa = MagicMock()
        mock_alsa.amixer_control.return_value = False
        self.driver.alsa = mock_alsa
        self.driver.get_cardid_deviceid = Mock(return_value=(0, 0))
        self.driver.get_control_numid = Mock(return_value=1)
    
        self.assertFalse(self.driver.enable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_asound.return_value.save_default_file.called)
        self.assertTrue(mock_alsa.amixer_control.called)
        self.assertFalse(mock_alsa.save.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_disable(self, mock_asound):
        self.init_session()
        mock_alsa = Mock()
        self.driver.alsa = mock_alsa
    
        self.assertTrue(self.driver.disable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_alsa.amixer_control.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_disable_alsa_amixer_control_failed(self, mock_asound):
        self.init_session()
        mock_alsa = Mock()
        mock_alsa.amixer_control.return_value = False
        self.driver.alsa = mock_alsa
    
        self.assertFalse(self.driver.disable())

        self.assertTrue(mock_alsa.amixer_control.called)
        self.assertFalse(mock_asound.return_value.delete.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_disable_asound_delete_failed(self, mock_asound):
        mock_asound.return_value.delete.return_value = False
        self.init_session()
        mock_alsa = Mock()
        self.driver.alsa = mock_alsa
    
        self.assertFalse(self.driver.disable())

        self.assertTrue(mock_asound.return_value.delete.called)
        self.assertTrue(mock_alsa.amixer_control.called)

    @patch('backend.bcm2835audiodriver.EtcAsoundConf')
    def test_is_enabled(self, mock_asound):
        self.init_session()

        self.driver.is_card_enabled = Mock(return_value=True)
        mock_asound.return_value.exists.return_value = True
        self.assertTrue(self.driver.is_enabled())

        self.driver.is_card_enabled = Mock(return_value=False)
        mock_asound.return_value.exists.return_value = True
        self.assertFalse(self.driver.is_enabled())

        self.driver.is_card_enabled = Mock(return_value=True)
        mock_asound.return_value.exists.return_value = False
        self.assertFalse(self.driver.is_enabled())

    def test_get_volumes(self):
        self.init_session()
        mock_alsa = Mock()
        mock_alsa.get_volume.return_value = 66
        self.driver.alsa = mock_alsa

        vols =  self.driver.get_volumes()
        self.assertEqual(vols, { 'playback': 66, 'capture': None })

    def test_set_volumes(self):
        self.init_session()
        mock_alsa = Mock()
        mock_alsa.set_volume.return_value = 99
        self.driver.alsa = mock_alsa

        vols = self.driver.set_volumes(playback=12, capture=34)
        self.assertEqual(vols, { 'playback': 99, 'capture': None })



if __name__ == "__main__":
    # coverage run --omit="*lib/python*/*","test_*" --concurrency=thread test_audio.py; coverage report -m -i
    unittest.main()
    
