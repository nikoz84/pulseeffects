# -*- coding: utf-8 -*-

import logging

import PulseEffects.libpulse as p
from gi.repository import GLib, GObject


class PulseManager(GObject.GObject):

    __gsignals__ = {
        'sink_input_added': (GObject.SIGNAL_RUN_FIRST, None,
                             (object,)),
        'sink_input_changed': (GObject.SIGNAL_RUN_FIRST, None,
                               (object,)),
        'sink_input_removed': (GObject.SIGNAL_RUN_FIRST, None,
                               (int,)),
        'source_output_added': (GObject.SIGNAL_RUN_FIRST, None,
                                (object,)),
        'source_output_changed': (GObject.SIGNAL_RUN_FIRST, None,
                                  (object,)),
        'source_output_removed': (GObject.SIGNAL_RUN_FIRST, None,
                                  (int,)),
        'source_added': (GObject.SIGNAL_RUN_FIRST, None,
                         ()),
        'source_changed': (GObject.SIGNAL_RUN_FIRST, None,
                           ()),
        'source_removed': (GObject.SIGNAL_RUN_FIRST, None,
                           ())
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.context_ok = False

        self.default_sink_idx = -1
        self.default_sink_name = ''
        self.default_sink_rate = -1
        self.default_sink_format = ''

        self.default_source_idx = -1
        self.default_source_name = ''
        self.default_source_rate = -1
        self.default_source_format = ''

        # these variables are used to get values inside pulseaudio's callbacks
        self.sink_is_loaded = False
        self.sink_owner_module = -1
        self.sink_idx = -1
        self.sink_rate = -1
        self.sink_format = ''
        self.sink_monitor_name = ''
        self.sink_monitor_idx = -1

        # these variables are used to get values inside pulseaudio's callbacks
        self.source_idx = -1
        self.source_rate = -1
        self.source_format = ''

        # we redirect sink inputs to this sink
        self.apps_sink_idx = -1
        self.apps_sink_owner_module = -1
        self.apps_sink_rate = -1
        self.apps_sink_format = ''
        self.apps_sink_monitor_name = ''
        self.apps_sink_monitor_idx = -1
        self.apps_sink_description = '\'PulseEffects(apps)\''

        # microphone processed output will be sent to this sink
        # we redirect source outputs to this sink monitor
        self.mic_sink_idx = -1
        self.mic_sink_owner_module = -1
        self.mic_sink_rate = -1
        self.mic_sink_format = ''
        self.mic_sink_monitor_name = ''
        self.mic_sink_monitor_idx = -1
        self.mic_sink_description = '\'PulseEffects(mic)\''

        self.max_volume = p.PA_VOLUME_NORM

        self.log = logging.getLogger('PulseEffects')

        # it makes no sense to show some kind of apps. So we blacklist them
        self.app_blacklist = ['PulseEffects', 'pulseeffects', 'gsd-media-keys',
                              'GNOME Shell', 'libcanberra', 'gnome-pomodoro',
                              'PulseAudio Volume Control', 'Screenshot']

        self.media_blacklist = ['pulsesink probe', 'bell-window-system',
                                'audio-volume-change', 'Peak detect',
                                'screen-capture']

        # wrapping callbacks
        self.ctx_notify_cb = p.pa_context_notify_cb_t(self.context_notify)
        self.server_info_cb = p.pa_server_info_cb_t(self.server_info)
        self.sink_info_cb = p.pa_sink_info_cb_t(self.sink_info)
        self.source_info_cb = p.pa_source_info_cb_t(self.source_info)
        self.sink_input_info_cb = p.pa_sink_input_info_cb_t(
            self.sink_input_info)
        self.source_output_info_cb = p.pa_source_output_info_cb_t(
            self.source_output_info)
        self.ctx_success_cb = p.pa_context_success_cb_t(self.ctx_success)
        self.subscribe_cb = p.pa_context_subscribe_cb_t(self.subscribe)

        # creating main loop and context
        self.main_loop = p.pa_threaded_mainloop_new()
        self.main_loop_api = p.pa_threaded_mainloop_get_api(self.main_loop)

        self.ctx = p.pa_context_new(self.main_loop_api, b'PulseEffects')

        p.pa_context_set_state_callback(self.ctx, self.ctx_notify_cb, None)

        p.pa_context_connect(self.ctx, None, 0, None)

        p.pa_threaded_mainloop_start(self.main_loop)

        # waiting context

        while self.context_ok is False:
            pass

        self.get_server_info()
        self.get_default_sink_info()
        self.get_default_source_info()

        # subscribing to pulseaudio events
        p.pa_context_set_subscribe_callback(self.ctx, self.subscribe_cb,
                                            None)

        subscription_mask = p.PA_SUBSCRIPTION_MASK_SINK_INPUT + \
            p.PA_SUBSCRIPTION_MASK_SOURCE_OUTPUT + \
            p.PA_SUBSCRIPTION_MASK_SOURCE

        p.pa_context_subscribe(self.ctx, subscription_mask,
                               self.ctx_success_cb, None)

    def get_sample_spec_format(self, code):
        if code == p.PA_SAMPLE_U8:
            return 'u8'
        elif code == p.PA_SAMPLE_ALAW:
            return 'alaw'
        elif code == p.PA_SAMPLE_ULAW:
            return 'ulaw'
        elif code == p.PA_SAMPLE_S16LE:
            return 's16le'
        elif code == p.PA_SAMPLE_S16BE:
            return 's16be'
        elif code == p.PA_SAMPLE_FLOAT32LE:
            return 'float32le'
        elif code == p.PA_SAMPLE_FLOAT32BE:
            return 'float32be'
        elif code == p.PA_SAMPLE_S32LE:
            return 's32le'
        elif code == p.PA_SAMPLE_S32BE:
            return 's32Be'
        elif code == p.PA_SAMPLE_S24LE:
            return 's24le'
        elif code == p.PA_SAMPLE_S24BE:
            return 's24be'
        elif code == p.PA_SAMPLE_S24_32LE:
            return 's24_32le'
        elif code == p.PA_SAMPLE_S24_32BE:
            return 's24_32be'
        elif code == p.PA_SAMPLE_MAX:
            return 'pa_max'
        elif code == p.PA_SAMPLE_INVALID:
            return 'invalid'

    def context_notify(self, ctx, user_data):
        state = p.pa_context_get_state(ctx)

        if state == p.PA_CONTEXT_READY:
            self.context_ok = True
            self.log.info('pulseaudio context started')
            self.log.info('connected to server: ' +
                          p.pa_context_get_server(ctx).decode())
            self.log.info('server protocol version: ' +
                          str(p.pa_context_get_server_protocol_version(ctx)))

        elif state == p.PA_CONTEXT_FAILED:
            self.log.critical('failed to start pulseaudio context')

        elif state == p.PA_CONTEXT_TERMINATED:
            self.log.info('pulseaudio context terminated')

    def exit(self):
        self.unload_sinks()

        self.log.info('sinks unloaded')

        self.log.info('disconnecting pulseaudio context')
        p.pa_context_disconnect(self.ctx)

        self.log.info('stopping pulseaudio threaded main loop')
        p.pa_threaded_mainloop_stop(self.main_loop)

        self.log.info('unferencing pulseaudio context object')
        p.pa_context_unref(self.ctx)

        self.log.info('freeing pulseaudio main loop object')
        p.pa_threaded_mainloop_free(self.main_loop)

    def load_sink_info(self, name):
        o = p.pa_context_get_sink_info_by_name(self.ctx, name.encode(),
                                               self.sink_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

    def load_source_info(self, name):
        o = p.pa_context_get_source_info_by_name(self.ctx, name.encode(),
                                                 self.source_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

    def get_server_info(self):
        o = p.pa_context_get_server_info(self.ctx, self.server_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

    def get_default_sink_info(self):
        self.load_sink_info(self.default_sink_name)

        self.default_sink_rate = self.sink_rate
        self.default_sink_idx = self.sink_idx
        self.default_sink_format = self.sink_format

        self.log.info('default pulseaudio sink audio format: ' +
                      str(self.default_sink_format))
        self.log.info('default pulseaudio sink sampling rate: ' +
                      str(self.default_sink_rate) +
                      ' Hz. We will use the same rate.')

    def get_default_source_info(self):
        self.load_source_info(self.default_source_name)

        self.default_source_rate = self.source_rate
        self.default_source_idx = self.source_idx
        self.default_source_format = self.source_format

        self.log.info('default pulseaudio source audio format: ' +
                      str(self.default_source_format))
        self.log.info('default pulseaudio source sampling rate: ' +
                      str(self.default_source_rate) +
                      ' Hz. We will use the same rate.')

    def server_info(self, context, info, user_data):
        self.default_sink_name = info.contents.default_sink_name.decode()
        self.default_source_name = info.contents.default_source_name.decode()

        server_version = info.contents.server_version.decode()

        self.log.info('pulseaudio version: ' + server_version)
        self.log.info('default pulseaudio source: ' + self.default_source_name)
        self.log.info('default pulseaudio sink: ' + self.default_sink_name)

    def sink_info(self, context, info, eol, user_data):
        if eol == -1:
            self.sink_is_loaded = False
        elif eol == 0:
            if info:
                self.sink_owner_module = info.contents.owner_module
                self.sink_idx = info.contents.index
                self.sink_rate = info.contents.sample_spec.rate

                sample_format = info.contents.sample_spec.format
                self.sink_format = self.get_sample_spec_format(sample_format)

                self.sink_monitor_name = info.contents.monitor_source_name\
                    .decode()

                self.sink_monitor_idx = info.contents.monitor_source
        elif eol == 1:
            self.sink_is_loaded = True

    def source_info(self, context, info, eol, user_data):
        if info:
            self.source_idx = info.contents.index
            self.source_rate = info.contents.sample_spec.rate

            sample_format = info.contents.sample_spec.format
            self.source_format = self.get_sample_spec_format(sample_format)

    def load_sink(self, name, description, rate):
        self.load_sink_info(name)

        if not self.sink_is_loaded:
            args = []

            sink_properties = description
            sink_properties += 'device.class=\'sound\''

            args.append('sink_name=' + name)
            args.append('sink_properties=' + sink_properties)
            args.append('channels=2')
            args.append('rate=' + str(rate))

            argument = ' '.join(map(str, args)).encode('ascii')

            module = b'module-null-sink'

            def module_idx(context, idx, user_data):
                self.log.info('sink owner module index: ' + str(idx))

            self.module_idx_cb = p.pa_context_index_cb_t(module_idx)

            o = p.pa_context_load_module(self.ctx, module, argument,
                                         self.module_idx_cb, None)

            while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
                pass

            p.pa_operation_unref(o)

            self.load_sink_info(name)

            if self.sink_is_loaded:
                return True
            else:
                return False
        else:
            self.load_sink_info(name)
            return True

    def load_apps_sink(self):
        self.log.info('loading Pulseeffects applications sink...')

        name = 'PulseEffects_apps'
        description = 'device.description=' + self.apps_sink_description
        rate = self.default_sink_rate

        status = self.load_sink(name, description, rate)

        if status:
            self.apps_sink_idx = self.sink_idx
            self.apps_sink_owner_module = self.sink_owner_module
            self.apps_sink_rate = self.sink_rate
            self.apps_sink_format = self.sink_format
            self.apps_sink_monitor_name = self.sink_monitor_name
            self.apps_sink_monitor_idx = self.sink_monitor_idx

            self.log.info('Pulseeffects apps sink was successfully loaded')
            self.log.info('Pulseeffects apps sink index:' +
                          str(self.apps_sink_idx))
            self.log.info('Pulseeffects apps sink monitor name: ' +
                          self.sink_monitor_name)
        else:
            self.log.critical('Could not load apps sink')

    def load_mic_sink(self):
        self.log.info('loading Pulseeffects microphone output sink...')

        name = 'PulseEffects_mic'
        description = 'device.description=' + self.mic_sink_description
        rate = self.default_source_rate

        status = self.load_sink(name, description, rate)

        if status:
            self.mic_sink_idx = self.sink_idx
            self.mic_sink_owner_module = self.sink_owner_module
            self.mic_sink_rate = self.sink_rate
            self.mic_sink_format = self.sink_format
            self.mic_sink_monitor_name = self.sink_monitor_name
            self.mic_sink_monitor_idx = self.sink_monitor_idx

            self.log.info('Pulseeffects mic sink was successfully loaded')
            self.log.info('Pulseeffects mic sink index:' +
                          str(self.mic_sink_idx))
            self.log.info('Pulseeffects mic sink monitor name: ' +
                          self.mic_sink_monitor_name)
        else:
            self.log.critical('Could not load mic sink')

    def sink_input_info(self, context, info, eol, user_data):
        if info:
            idx = info.contents.index
            connected_sink_idx = info.contents.sink

            proplist = info.contents.proplist

            app_name = p.pa_proplist_gets(proplist, b'application.name')
            media_name = p.pa_proplist_gets(proplist, b'media.name')
            icon_name = p.pa_proplist_gets(proplist, b'application.icon_name')

            if not app_name:
                app_name = ''
            else:
                app_name = app_name.decode()

            if not media_name:
                media_name = ''
            else:
                media_name = media_name.decode()

            if (app_name not in self.app_blacklist and
                    media_name not in self.media_blacklist):
                if not icon_name:
                    icon_name = 'audio-x-generic-symbolic'
                else:
                    icon_name = icon_name.decode()

                connected = False
                if connected_sink_idx == self.apps_sink_idx:
                    connected = True

                volume = info.contents.volume
                audio_channels = volume.channels
                mute = info.contents.mute

                max_volume_linear = 100 * \
                    p.pa_cvolume_max(volume) / p.PA_VOLUME_NORM

                resample_method = info.contents.resample_method

                if resample_method:
                    resample_method = resample_method.decode()
                else:
                    resample_method = 'null'

                sample_spec = info.contents.sample_spec
                rate = sample_spec.rate
                sample_format = self.get_sample_spec_format(sample_spec.format)

                new_input = [idx, app_name, media_name,
                             icon_name, audio_channels, max_volume_linear,
                             rate, resample_method, sample_format, mute,
                             connected]

                if user_data == 1:
                    GLib.idle_add(self.emit, 'sink_input_added', new_input)
                elif user_data == 2:
                    GLib.idle_add(self.emit, 'sink_input_changed', new_input)

    def source_output_info(self, context, info, eol, user_data):
        if info:
            idx = info.contents.index
            connected_source_idx = info.contents.source

            proplist = info.contents.proplist

            app_name = p.pa_proplist_gets(proplist, b'application.name')
            media_name = p.pa_proplist_gets(proplist, b'media.name')
            icon_name = p.pa_proplist_gets(proplist, b'application.icon_name')

            if not app_name:
                app_name = ''
            else:
                app_name = app_name.decode()

            if not media_name:
                media_name = ''
            else:
                media_name = media_name.decode()

            if (app_name not in self.app_blacklist and
                    media_name not in self.media_blacklist):
                if not icon_name:
                    icon_name = 'audio-x-generic-symbolic'
                else:
                    icon_name = icon_name.decode()

                connected = False
                if connected_source_idx == self.mic_sink_monitor_idx:
                    connected = True

                volume = info.contents.volume
                audio_channels = volume.channels
                mute = info.contents.mute

                max_volume_linear = 100 * \
                    p.pa_cvolume_max(volume) / p.PA_VOLUME_NORM

                resample_method = info.contents.resample_method

                if resample_method:
                    resample_method = resample_method.decode()
                else:
                    resample_method = 'null'

                sample_spec = info.contents.sample_spec
                rate = sample_spec.rate
                sample_format = self.get_sample_spec_format(sample_spec.format)

                new_output = [idx, app_name, media_name,
                              icon_name, audio_channels, max_volume_linear,
                              rate, resample_method, sample_format, mute,
                              connected]

                if user_data == 1:
                    GLib.idle_add(self.emit, 'source_output_added', new_output)
                elif user_data == 2:
                    GLib.idle_add(self.emit, 'source_output_changed',
                                  new_output)

    def find_sink_inputs(self):
        p.pa_context_get_sink_input_info_list(self.ctx,
                                              self.sink_input_info_cb,
                                              1)  # 1 for new

    def find_source_outputs(self):
        p.pa_context_get_source_output_info_list(self.ctx,
                                                 self.source_output_info_cb,
                                                 1)  # 1 for new

    def move_sink_input_to_pulseeffects_sink(self, idx):
        p.pa_context_move_sink_input_by_index(self.ctx, idx,
                                              self.apps_sink_idx,
                                              self.ctx_success_cb, None)

    def move_sink_input_to_default_sink(self, idx):
        p.pa_context_move_sink_input_by_name(self.ctx, idx,
                                             self.default_sink_name.encode(),
                                             self.ctx_success_cb, None)

    def move_source_output_to_pulseeffects_source(self, idx):
        p.pa_context_move_source_output_by_index(self.ctx, idx,
                                                 self.mic_sink_monitor_idx,
                                                 self.ctx_success_cb, None)

    def move_source_output_to_default_source(self, idx):
        p.pa_context_move_source_output_by_name(self.ctx, idx,
                                                self.default_source_name
                                                .encode(),
                                                self.ctx_success_cb, None)

    def set_sink_input_volume(self, idx, audio_channels, value):
        cvolume = p.pa_cvolume()
        cvolume.channels = audio_channels

        raw_value = int(p.PA_VOLUME_NORM * value / 100)

        cvolume_ptr = p.pa_cvolume_set(p.get_pointer(cvolume), audio_channels,
                                       raw_value)

        p.pa_context_set_sink_input_volume(self.ctx, idx, cvolume_ptr,
                                           self.ctx_success_cb, None)

    def set_sink_input_mute(self, idx, mute_state):
        p.pa_context_set_sink_input_mute(self.ctx, idx, mute_state,
                                         self.ctx_success_cb, None)

    def set_source_output_volume(self, idx, audio_channels, value):
        cvolume = p.pa_cvolume()
        cvolume.channels = audio_channels

        raw_value = int(p.PA_VOLUME_NORM * value / 100)

        cvolume_ptr = p.pa_cvolume_set(p.get_pointer(cvolume), audio_channels,
                                       raw_value)

        p.pa_context_set_source_output_volume(self.ctx, idx, cvolume_ptr,
                                              self.ctx_success_cb, None)

    def set_source_output_mute(self, idx, mute_state):
        p.pa_context_set_source_output_mute(self.ctx, idx, mute_state,
                                            self.ctx_success_cb, None)

    def subscribe(self, context, event_value, idx, user_data):
        event_facility = event_value & p.PA_SUBSCRIPTION_EVENT_FACILITY_MASK

        if event_facility == p.PA_SUBSCRIPTION_EVENT_SINK_INPUT:
            event_type = event_value & p.PA_SUBSCRIPTION_EVENT_TYPE_MASK

            if event_type == p.PA_SUBSCRIPTION_EVENT_NEW:
                p.pa_context_get_sink_input_info(self.ctx, idx,
                                                 self.sink_input_info_cb,
                                                 1)  # 1 for new
            elif event_type == p.PA_SUBSCRIPTION_EVENT_CHANGE:
                p.pa_context_get_sink_input_info(self.ctx, idx,
                                                 self.sink_input_info_cb,
                                                 2)  # 2 for changes
            elif event_type == p.PA_SUBSCRIPTION_EVENT_REMOVE:
                GLib.idle_add(self.emit, 'sink_input_removed', idx)
        elif event_facility == p.PA_SUBSCRIPTION_EVENT_SOURCE_OUTPUT:
            event_type = event_value & p.PA_SUBSCRIPTION_EVENT_TYPE_MASK

            if event_type == p.PA_SUBSCRIPTION_EVENT_NEW:
                p.pa_context_get_source_output_info(self.ctx, idx,
                                                    self.source_output_info_cb,
                                                    1)  # 1 for new
            elif event_type == p.PA_SUBSCRIPTION_EVENT_CHANGE:
                p.pa_context_get_source_output_info(self.ctx, idx,
                                                    self.source_output_info_cb,
                                                    2)  # 1 for new
            elif event_type == p.PA_SUBSCRIPTION_EVENT_REMOVE:
                GLib.idle_add(self.emit, 'source_output_removed', idx)
        elif event_facility == p.PA_SUBSCRIPTION_EVENT_SOURCE:
            event_type = event_value & p.PA_SUBSCRIPTION_EVENT_TYPE_MASK

            if event_type == p.PA_SUBSCRIPTION_EVENT_NEW:
                GLib.idle_add(self.emit, 'source_added')
            elif event_type == p.PA_SUBSCRIPTION_EVENT_CHANGE:
                GLib.idle_add(self.emit, 'source_changed')
            elif event_type == p.PA_SUBSCRIPTION_EVENT_REMOVE:
                GLib.idle_add(self.emit, 'source_removed')

    def ctx_success(self, context, success, user_data):
        if not success:
            self.log.critical('context operation failed!!')

    def unload_sinks(self):
        p.pa_context_unload_module(self.ctx, self.apps_sink_owner_module,
                                   self.ctx_success_cb, None)

        p.pa_context_unload_module(self.ctx, self.mic_sink_owner_module,
                                   self.ctx_success_cb, None)
