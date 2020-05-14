
import argparse
import time
import types
from pprint import pprint

import mido
import music21
from music21.stream import Score
from music21.note import Note
from music21.midi import DeltaTime, MidiEvent, MidiTrack
# docs seem out of date on name of this. first c is capital in docs i think.
from music21.midi import channelVoiceMessages as CVM


# TODO experiment w/ external instrument channel settings and see if different
# data gets through
# (test pitch bends + other stuff)

# TODO maybe one test comparing my input into music21 vs. saving full instrument
# clip to some kind of midi file in ableton, and then parsing that more directly
# w/ fns available in music21
# i.e. score = converter.parse(‘path/to/file.mid’)
# https://web.mit.edu/music21/doc/moduleReference/moduleMidiTranslate.html

# TODO TODO TODO possible to use some combination of stuff accessible through
# WSL and windows to get some virtual midi ports?

# TODO TODO TODO is there a way to get the bpm from ableton midi?
# TODO try monitoring MIDI output while changing tempo in ableton to see if the
# MIDI contains some data on this
# TODO does ableton maybe only send tempo update midi stuff if it deviates from
# this default (120)? or does it just never send that over midi / am i just not
# getting it?
bpm = 120

# I don't think it should matter if this is more precise than the MIDI inputs
# (apart from possible downstream time costs). Could try to estimate this
# resolution of the MIDI input (though not if it's manually controlled)?
# Using the "common value" mentioned in the `mido` docs.
ticks_per_quarter_note = 1024

# The "beat" in [b]pm means a quarter note, not a whole note.
#ticks_per_beat = ticks_per_quarter_note * 4
ticks_per_beat = ticks_per_quarter_note
beats_per_second = bpm / 60.
ticks_per_second = ticks_per_beat * beats_per_second

# TODO get time in secs from first message and then subtract that offset from
# all future times (if we have it, though shouldn't be calling this if we
# don't...)
def secs2ticks(seconds_from_start, offset_s=0.0):
    """Converts time representation from `float` seconds to `int` ticks.
    """
    return int(round(seconds_from_start * ticks_per_second - offset_s))


# TODO rename to reflect it will update as it gets a sufficient amount of
# messages for each update (at a note off for each on, etc)
first_message_time_s = None
curr_time_s = 0.0
# TODO TODO test case where a note actually starts (for example) a quarter note
# past 1.1.1 in ableton (or anything > 1.1.1)
last_ticks = 0
# TODO test w/ at least pitch bends, if i want to support that.
# other cases with issues?
note_num2start_data = dict()
# TODO why was index required here? docs seem to indicate it's a kwarg....
midi_track = MidiTrack(0)
# TODO TODO worth converting the stream to a score? if so, what fns to use?
def process_msg(msg):
    """
    Adds a new `music21.midi.Note` to `score` (`music21.stream.Score`) if it
    complete a note, otherwise just updates `curr_time_s`.

    Argument `msg` should be a `mido.Message`
    """
    global first_message_time_s
    global last_ticks
    global curr_time_s
    if first_message_time_s is None:
        first_message_time_s = msg.time

    # This is assuming that the time is tracked by adding all the delta times
    # that I ultimately get from rtmidi.
    # TODO need to check if the msg has this attribute?
    curr_time_s += msg.time

    # TODO also extend to those midi pads? requires that ~polytouch type, right?
    if msg.type not in ('note_on', 'note_off'):
        return

    # TODO TODO deal w/ pitch bends and stuff like that. music21 docs seem to
    # indicate some of its fns already deal with that, so i feel like i'm not
    # taking full advantage of the functionality already in the library...

    # TODO TODO TODO how to use deltatime w/o drifting away from true bpm due to
    # rounding????? (actually, how i'm doing it might be fine. check!!!)

    # TODO TODO TODO check assumption that delta time increments between each
    # msg (how do the ableton clock messages help then? how would i use any info
    # they have to improve current midi time est? is it just a matter of how
    # frequently they are received, or do they have other info that maybe i'm
    # just not getting?)
    # TODO TODO TODO if there is a quarter note in every position from 1.1.1,
    # this should equal ticks_per_quarter note at the note_off for the first
    # quarter note. why is it 4571 rather than 1024=ticks_per_quarter_note???
    ticks = secs2ticks(curr_time_s, offset_s=first_message_time_s)
    print('ticks:', ticks)
    d_ticks = ticks - last_ticks
    print('d_ticks:', d_ticks)

    # The conditional above should guarantee this `note` attribute exists.
    note_num = msg.note
    # Generating approprate input for `midiEventsToNote` as specified in
    # `music21` docs.
    # TODO TODO check, but it seems like rtmidi 0 indexes these, while ableton
    # and mido 1-index them?
    channel = msg.channel + 1
    if msg.type == 'note_on':
        assert note_num not in note_num2start_data
        # TODO any reason not to specify the channel?
        #delta1 = DeltaTime(midi_track, time=d_ticks, channel=msg.channel)
        delta1 = DeltaTime(midi_track, time=d_ticks)

        # TODO TODO leaving type=None of default OK? does that select some
        # appropriate version of the "ChannelVoiceMessages" the docs talk about?
        # TODO TODO del tim=0 here and below once i figure out whawt was causing
        # "type NoneType doesn't define __round__ method" error...
        on = MidiEvent(midi_track, type=CVM.NOTE_ON, channel=channel, time=0)
        # TODO refactor?
        print('msg.note:', msg.note)
        on.pitch = msg.note
        # TODO TODO TODO why is this None despite being set to an int?
        print('on.pitch:', on.pitch)
        print()
        on.velocity = msg.velocity

        note_num2start_data[note_num] = (ticks, delta1, on)

    elif msg.type == 'note_off':
        abs_on_ticks, delta1, on = note_num2start_data[note_num]
        # TODO TODO TODO or should this be from the last midi event???
        # that feels more consistent... (though it also seems harder for music21
        # to handle that...)
        # TODO TODO maybe test w/ single notes first
        # TODO delete ticks from start_data if not used
        #d_ticks = ticks - abs_on_ticks

        # TODO how are tracks used? will i only ever want one?

        # TODO see CVM.PITCH_BEND re: how to handle pitch bends (though prob.
        # not a complete solution right there...)

        #delta2 = DeltaTime(midi_track, time=d_ticks, channel=msg.channel)
        delta2 = DeltaTime(midi_track, time=d_ticks)

        # TODO why are there `time` fields for MidiEvent, if DeltaTime
        # is used for midiEventsToNote? (docs say it's non-essential as
        # DeltaTime is more important, so prob shouldn't worry)
        off = MidiEvent(midi_track, type=CVM.NOTE_OFF, channel=channel, time=0)
        # These variables aren't in the constructor (at least accoring to the
        # docs) for some reason.
        # TODO need to remap the range here, or good as-is?
        off.pitch = msg.note
        print('off.pitch:', off.pitch)
        off.velocity = msg.velocity

        # TODO need to set the ticksPerQuarter=None kwarg to this? and how
        # should i derive the appropriate input from the midi data i'm getting
        # from ableton? (i think i should set it, yes, but what happens if i
        # don't?)
        try:
            note = music21.midi.translate.midiEventsToNote(
                [delta1, on, delta2, off], ticksPerQuarter=ticks_per_quarter_note
                #[(delta1, on), (delta2, off)], ticksPerQuarter=ticks_per_quarter_note
            )
            print('WORKED!')
        except:
            print(delta1)
            print(on)
            print(delta2)
            print(off)
            print(ticks_per_quarter_note)
            raise
            import ipdb; ipdb.set_trace()

        del note_num2start_data[note_num]

    last_ticks = ticks


def add_rtmdi_msgin_deltatime():
    """
    Patches `mido` to add deltatime (s) to the `time` field of `rtmidi` backend
    input messages.

    Makes sense unless I missed some way to enable the correct MIDI timestamps
    without monkey-patching `mido`...
    """
    old_callback_wrapper = mido.backends.rtmidi.Input._callback_wrapper
    def new_callback_wrapper(self, msg_data, data):
        from mido.messages import Message
        # I copied this from the body of the old callback in the `mido` source,
        # rather than calling it, because I needed access to the `msg`
        # variable, and in the case where `self._callback` is defined, I may not
        # be able to rely on `msg` being at the end of `self._queue`.
        try:
            msg = Message.from_bytes(msg_data[0])
        except ValueError:
            # Ignore invalid message.
            return

        # (Actually storing the DELTA time here, because otherwise I'd just need
        # to conver to this anyway, and that's all I'd use `msg.time` for.)
        msg.time = msg_data[1]

        # (also copied from `mido` source)
        (self._callback or self._queue.put)(msg)

    mido.backends.rtmidi.Input._callback_wrapper = new_callback_wrapper


def main(through_virtual=True, debug=True):
    loopbe_prefix = 'LoopBe Internal MIDI '
    if through_virtual:
        input_names = [n for n in mido.get_input_names()
            if n.startswith(loopbe_prefix)
        ]
        assert len(input_names) == 1
    else:
        input_names = [n for n in mido.get_input_names()
            if not n.startswith(loopbe_prefix)
        ]
        if len(input_names) == 0:
            raise IOError('no input devices found')
        elif len(input_names) > 1:
            print('Input devices:')
            pprint(input_devices)
            raise IOError('too many input devices found')
    input_name = input_names[0]

    # TODO TODO how to correspond note ons to note offs? just always 1 after the
    # other, never w/ intervening note ons (for a given note #)?
    # are the drum pads an exception to this ("polytouch"?)?

    add_rtmdi_msgin_deltatime()

    print(f'Input device: {input_name}')
    messages = []
    try:
        with mido.open_input(input_name) as inport:
            #for msg in inport:
            while True:
                # Using this non-blocking iteration inside of the while loop to 
                # give Python more opportunities to process the
                # KeyboardInterrupt (test).
                # (maybe it was just a matter of not knowing the correct ctrl
                # sequence of characters to trigger KeyboardInterrupt in
                # windows? or some windows latency?)
                for msg in inport.iter_pending():
                    # TODO is the msg.time field correct? maybe the loopback
                    # device is mangling that data? (no probably just the norm
                    # for live MIDI...)
                    # TODO check against direct input from arturia? (same)
                    # TODO worst case scenario, use a translated time.time() or
                    # something?
                    messages.append(msg)
                    print(msg)
                    process_msg(msg)

    # TODO also compare music21 "clip" (in terms of sum of time errors?) vs both
    # seq of loopbe outputs timestamped w/ time.time() AND ableton midi
    # recording of SAME playthrough of a preset ableton clip
    # (try not preset too, if directly using a midi input as midi output changes
    # the latency calculation)

    # something that doesn't take as long? or is something else causing that?
    # TODO TODO maybe it's the mido input IO that is blocking? check the
    # non-blocking versions of those calls?
    except KeyboardInterrupt:
        print('\nSet of message types seen so far:',
            {m.type for m in messages if hasattr(m, 'channel')}
        )
        print('Set of channels seen so far:',
            {m.channel for m in messages if hasattr(m, 'channel')}
        )
        # TODO TODO if this isn't it, figure out how to translate from the
        # rtmidi deltatimes to delta ticks suitable for music21
        # TODO TODO subtract at least first offset, probably also everything
        # after last note_off
        sum_s = sum([m.time for m in messages])
        print(f'Sum of rtmidi deltatimes: {sum_s:.2f}s')
        print()
        # TODO should i just specify ticks per quarter either here or above?
        stream = music21.midi.translate.midiTrackToStream(midi_track,
            ticksPerQuarter=ticks_per_quarter_note
        )
        if debug:
            import ipdb; ipdb.set_trace()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--direct', action='store_true',
        help='Expects direct MIDI input (rather than through virtual device), '
        'for testing.'
    )
    parser.add_argument('-n', '--no-debug', action='store_true')
    args = parser.parse_args()
    main(through_virtual=not args.direct, debug=not args.no_debug)

