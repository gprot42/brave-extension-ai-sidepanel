#include <algorithm>
#include <arpa/inet.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#ifdef __APPLE__
#include "macos_endian.h"
#else
#include <endian.h>
#endif
#include <iostream>
#include <map>
#include <math.h>
#include <string>
#include <vector>

#define NUM_AMIGA_CHANNELS 4

extern "C" {
#include "../src/include/write_audio_ext.h"
}

using std::map;
using std::string;
using std::vector;

namespace {

const float EPSILON = 1e-10;

const uint32_t SAMPLES_PER_FRAME = 640;
const uint32_t PIXELS_PER_SAMPLE = 2;

const uint32_t SOUNDTICKS_PAL = 3546895;
const uint32_t AMIGA_FRAME_TICKS = SOUNDTICKS_PAL / 50;
const uint32_t AMIGA_PIXEL_TICKS = AMIGA_FRAME_TICKS / SAMPLES_PER_FRAME;

size_t VIDEO_FRAME_TICKS;

class Channel {
public:
	Channel() : value_(0), len_(0), per_(0), lc_(0), buffer_nr_(0) {}

	void advance_time(const int tdelta) {
		for (int i = 0; i < tdelta; i++)
			time_window_.push_back(value_);

		for (int i = 0; i < tdelta; i++)
			meta_window_.push_back(buffer_nr_);
	}

	void poll_time_window(
		vector<int16_t> *returned_time_window,
		vector<uint16_t> *returned_meta_window) {
		// TODO: Clean this. The buffering is the same for all
		// channels, so calculating the ticks should be done only once.
		const size_t ticks = 3 * AMIGA_FRAME_TICKS / 2 + 1;
		const size_t threshold_size = std::max(ticks,
						       VIDEO_FRAME_TICKS);
		if (time_window_.size() >= threshold_size) {
			// This is only done once in the beginning of the
			// stream
			returned_time_window->assign(
				time_window_.begin(),
				time_window_.begin() + ticks);
			assert(time_window_.size() >= VIDEO_FRAME_TICKS);

			returned_meta_window->assign(
				meta_window_.begin(),
				meta_window_.begin() + ticks);
			assert(meta_window_.size() >=
			       VIDEO_FRAME_TICKS);

			// Drop output video frame time equivalent of Paula
			// outputs
			time_window_.erase(
				time_window_.begin(),
				time_window_.begin() + VIDEO_FRAME_TICKS);

			meta_window_.erase(
				meta_window_.begin(),
				meta_window_.begin() + (
					VIDEO_FRAME_TICKS));
		}
	}

	int16_t value_;
	int len_;
	int per_;
	uint32_t lc_;
	uint16_t buffer_nr_;
	vector<int16_t> time_window_;
	vector<uint16_t> meta_window_;
	vector<float> previous_frame_signal_;
};


class AudioChannels {
public:
	AudioChannels() {}

	Channel channels_[4];
	int outputs_[2];
	map<uint32_t, uint16_t> address_to_buffer_nr_;
};

class Settings {
public:
	Settings() {}

	uint32_t fps = 60;
	int sample_rate = 44100;  // hardcoded into wav
	string wave_path;
	float panning = 0.7;
};


void handle_paula_channel_output(AudioChannels *channels,
				 const struct uade_write_audio_frame &frame)
{
	// Handle Audio channel output
	for (int i = 0; i < NUM_AMIGA_CHANNELS; i++) {
		channels->channels_[i].value_ = static_cast<int16_t>(
			ntohs(frame.data.output[i]));
	}
}

void handle_paula_event(AudioChannels *channels, FILE *wave_file,
			const struct uade_write_audio_frame &frame,
			const Settings &settings)
{
	const struct uade_paula_event_frame *pef = (
		&frame.data.paula_event_frame);
	auto channel_nr = pef->channel;
	assert(channel_nr >= 0 and channel_nr < NUM_AMIGA_CHANNELS);
	auto event_type = static_cast<enum UADEPaulaEventType>(
		pef->event_type);

	uint16_t event_value = ntohs(pef->event_value);
	Channel *channel = &channels->channels_[channel_nr];

	switch (event_type) {
	case PET_LEN:
		channel->len_ = event_value;
		break;
	case PET_LCH:
		channel->lc_ = (((uint32_t) event_value) << 16) | (
			channel->lc_ & 0xffff);
		break;
	case PET_LCL:
		channel->lc_ = (channel->lc_ & 0xffff0000) | event_value;
		break;
	case PET_PER:
		channel->per_ = event_value;
		break;
	case PET_OUTPUT:
		assert(channel_nr <= 1);
		channels->outputs_[channel_nr] = event_value;
		if (channel_nr == 1) {
			unsigned char wave_frame[4];

			// Convert audio channel output from biased PCM
			// in range [0, 65535] to integer range [-32768, 32767]
			int left = channels->outputs_[0];
			int right = channels->outputs_[1];
			if (left >= 32768)
				left -= 65536;
			if (right >= 32768)
				right -= 65536;

			// Do panning
			const int m = (right - left) * settings.panning;
			left += m;
			right -= m;

			const int serialized_left = (uint16_t) left;
			const int serialized_right = (uint16_t) right;
			wave_frame[0] = serialized_left & 0xff;
			wave_frame[1] = serialized_left >> 8;
			wave_frame[2] = serialized_right & 0xff;
			wave_frame[3] = serialized_right >> 8;
			ssize_t ret = fwrite(&wave_frame, 4, 1, wave_file);
			assert(ret == 1);
			channels->outputs_[0] = 0;
			channels->outputs_[1] = 0;
		}
		break;
	case PET_START_BUFFER:
		if (channels->address_to_buffer_nr_.find(channel->lc_) ==
		    channels->address_to_buffer_nr_.end()) {
			uint16_t buffer_nr = (
				channels->address_to_buffer_nr_.size());
			channels->address_to_buffer_nr_[channel->lc_] = (
				buffer_nr);
		}
		channel->buffer_nr_ = channels->address_to_buffer_nr_.at(
			channel->lc_);
		break;
	default:
		break;
	}
}

void integrate(vector<float> *signal, vector<uint16_t> *meta,
	       const vector<int16_t> &time_window,
	       const vector<uint16_t> &meta_window)
{
	signal->clear();
	meta->clear();

	// Split time_window into constant size segments, integrate the
	// segments that represent screen pixels, and normalize the integral.
	// The segment size is AMIGA_PIXEL_TICKS.
	size_t i = 0;
	const double multiplier = 1.0 / (AMIGA_PIXEL_TICKS * 64 * 128);
	while (true) {
		const size_t end = i + AMIGA_PIXEL_TICKS;
		if (end > time_window.size())
			break;

		meta->push_back(meta_window.at(i));

		int64_t sum = 0;
		for (; i < end; i++)
			sum += time_window[i];
		const double x = sum * multiplier;
		assert(x >= -1.0 and x <= 1.0);
		signal->push_back(x);
	}
}

float evaluate_cut_cost(const vector<float> &signal, const size_t trigger_point,
			const vector<float> &previous_frame_signal)
{
	const ssize_t CENTERING = SAMPLES_PER_FRAME / 2;
	assert(signal.size() >= (trigger_point + CENTERING));
	assert(previous_frame_signal.size() == SAMPLES_PER_FRAME);
	float sum = 0.0;
	for (size_t i = 0; i < CENTERING; i++) {
		const float delta = signal[trigger_point + i] - (
			previous_frame_signal[CENTERING + i]);
		sum += delta * delta;
	}
	return sum;
}

void trigger(vector<float> *signal,
	     vector<uint16_t> *meta,
	     const vector<float> &previous_frame_signal)
{
	int trigger_state = 0;
	const size_t CENTERING = SAMPLES_PER_FRAME / 2;
	size_t best_cut_point = 0;
	float best_cut_cost = -1.0;

	for (size_t i = CENTERING; i < SAMPLES_PER_FRAME; i++) {
		const float x = signal->at(i);
		if (trigger_state == 0) {
			if (x < 0.0)
				trigger_state = 1;
		} else if (x >= 0.0) {
			assert(trigger_state == 1);
			if (previous_frame_signal.size() > 0) {
				const float cut_cost = evaluate_cut_cost(
					*signal, i, previous_frame_signal);
				if (best_cut_cost < 0.0 or
				    cut_cost < best_cut_cost) {
					best_cut_cost = cut_cost;
					assert(i >= CENTERING);
					best_cut_point = i - CENTERING;
				}
			}
			trigger_state = 0;
		}
	}

	assert((best_cut_point + SAMPLES_PER_FRAME) <= signal->size());

	*signal = vector<float>(
		signal->begin() + best_cut_point,
		signal->begin() + best_cut_point + SAMPLES_PER_FRAME);

	*meta = vector<uint16_t>(
		meta->begin() + best_cut_point,
		meta->begin() + best_cut_point + SAMPLES_PER_FRAME);

	assert(signal->size() == SAMPLES_PER_FRAME);
	assert(meta->size() == SAMPLES_PER_FRAME);
}

void advance_time_on_channel(
	vector<float> *signal,
	vector<uint16_t> *meta,
	Channel *channel, const int tdelta)
{
	signal->clear();
	meta->clear();

	channel->advance_time(tdelta);

	vector<int16_t> time_window;
	vector<uint16_t> meta_window;

	channel->poll_time_window(&time_window, &meta_window);

	if (time_window.size() > 0) {
		integrate(signal, meta, time_window, meta_window);

		trigger(signal, meta, channel->previous_frame_signal_);

		// Record this frame's signal to be used for triggering
		// in the next frame
		channel->previous_frame_signal_ = *signal;
	}
}


void advance_time(AudioChannels *audio_channels, uint32_t tdelta)
{
	if (tdelta == 0)
		return;

	vector<vector<float> > signals;
	vector<vector<uint16_t> > metas;
	for (auto &channel : audio_channels->channels_) {
		vector<float> signal;
		vector<uint16_t> meta;
		advance_time_on_channel(&signal, &meta, &channel, tdelta);
		if (signal.size() > 0) {
			signals.push_back(signal);
			metas.push_back(meta);
		}
	}

	if (signals.size() == 0)
		return;

	assert(signals.size() == NUM_AMIGA_CHANNELS);

	for (int i = 0; i < NUM_AMIGA_CHANNELS; i++) {
		size_t num_written = fwrite(signals[i].data(), sizeof(float),
					    signals[i].size(), stdout);
		assert(num_written == SAMPLES_PER_FRAME);
	}

	for (int i = 0; i < NUM_AMIGA_CHANNELS; i++) {
		vector<unsigned short> meta;
		for (const auto &buffer_nr : metas[i])
			meta.push_back(buffer_nr);
		size_t num_written = fwrite(meta.data(), sizeof(meta[0]),
					    meta.size(), stdout);
		assert(num_written == SAMPLES_PER_FRAME);
	}
}

void write_le32(FILE *f, const uint32_t x)
{
	unsigned char buf[4];
	buf[0] = x & 0xff;
	buf[1] = x >> 8;
	buf[2] = x >> 16;
	buf[3] = x >> 24;
	size_t ret = fwrite(buf, 4, 1, f);
	assert(ret == 1);
}

}  // anonymous namespace

int main(int argc, char *argv[])
{
	vector<string> files;
	Settings settings;
	bool process_options = true;

	for (int i = 1; i < argc; ) {
		string s(argv[i]);
		if (process_options and s[0] == '-') {
			if (s == "--fps") {
				assert(((i + 1) < argc));
				settings.fps = atoi(argv[i + 1]);
				assert(settings.fps > 0);
				i += 2;
			} else if (s == "--panning") {
				assert(((i + 1) < argc));
				settings.panning = std::stof(argv[i + 1]);
				assert(settings.panning >= 0 &&
				       settings.panning <= 2);
				i += 2;
			} else if (s == "--wave") {
				assert(((i + 1) < argc));
				assert(settings.wave_path.size() == 0);
				settings.wave_path = argv[i + 1];
				i += 2;
			} else if (s == "--") {
				process_options = false;
				i++;
			} else {
				assert(0);
			}
		} else {
			files.push_back(s);
			i++;
		}
	}

	assert(files.size() <= 1);

	if (files.size() == 0)
		return 0;

	if (settings.wave_path.size() == 0) {
		fprintf(stderr, "Need wave path: --wave path\n");
		exit(1);
	}
	
	VIDEO_FRAME_TICKS = SOUNDTICKS_PAL / settings.fps;

	assert((SAMPLES_PER_FRAME * PIXELS_PER_SAMPLE) == 1280);

	FILE *reg_file = fopen(files[0].c_str(), "rb");
	assert(reg_file != nullptr);

	const size_t HEADER_SIZE = 16;
	uint8_t header[HEADER_SIZE];
	size_t sizeread = fread(header, HEADER_SIZE, 1, reg_file);
	assert(sizeread == 1);
	if (memcmp(header, "uade_osc_0\x00\xec\x17\x31\x03\x09",
		   HEADER_SIZE)) {
		fprintf(stderr, "No magic header found in %s\n",
			files[0].c_str());
		exit(1);
	}

	FILE *wave_file = fopen(settings.wave_path.c_str(), "wb");
	assert(wave_file != nullptr);

        // See https://docs.fileformat.com/audio/wav/

	// Later write size after RIFF at offset 4
	size_t sizewrite = fwrite("RIFF\x00\x00\x00\x00WAVEfmt ", 16, 1,
				  wave_file);
	assert(sizewrite == 1);
	sizewrite = fwrite("\x10\x00\x00\x00\x01\x00\x02\x00", 8, 1,
			   wave_file);
	assert(sizewrite == 1);

	// sample rate in LE binary
	const uint32_t sample_rate_le = htole32(settings.sample_rate);
	sizewrite = fwrite(&sample_rate_le, sizeof(sample_rate_le), 1,
			   wave_file);
	assert(sizewrite == 1);

	const uint32_t audio_frame_size = 4;
	const uint32_t bytes_per_second_le = htole32(
		settings.sample_rate * audio_frame_size);
	sizewrite = fwrite(&bytes_per_second_le, 4, 1, wave_file);
	assert(sizewrite == 1);

	// audio frame size in bytes
	const uint16_t audio_frame_size_le = htole32(audio_frame_size);
	sizewrite = fwrite(&audio_frame_size_le, 2, 1, wave_file);
	assert(sizewrite == 1);

	// 16 bits per sample
	sizewrite = fwrite("\x10\x00", 2, 1, wave_file);
	assert(sizewrite == 1);

	sizewrite = fwrite("data", 4, 1, wave_file);
	assert(sizewrite == 1);

	// Later write size after data at offset 40
	sizewrite = fwrite("\x00\x00\x00\x00", 4, 1, wave_file);
	assert(sizewrite == 1);

	AudioChannels audio_channels;

	sizewrite = fwrite(&settings.fps, sizeof(settings.fps), 1, stdout);
	assert(sizewrite == 1);

	const size_t samples_per_frame = SAMPLES_PER_FRAME;
	// Note: write native endianess, native size_t sive
	sizewrite = fwrite(&samples_per_frame, sizeof(samples_per_frame), 1,
			   stdout);
	assert(sizewrite == 1);

	// Note: write native endianess, size_t number of Amiga frames
	//
	// TODO: Implement calculation of num_frames for progress meter.
	const size_t num_frames = 0;
	sizewrite = fwrite(&num_frames, sizeof(num_frames), 1, stdout);
	assert(sizewrite == 1);

	while (1) {
		struct uade_write_audio_frame frame;
		size_t sizeread = fread(&frame, sizeof(frame), 1, reg_file);
		if (sizeread == 0)
			break;
		const uint32_t tdeltawhole  = ntohl(frame.tdelta);
		// Read an unsigned 24-bit time delta value
		const uint32_t tdelta = tdeltawhole & 0xffffff;
		advance_time(&audio_channels, tdelta);

		const uint32_t tdelta_control = tdeltawhole >> 24;
		if (tdelta_control == 0) {
			// This frame contains new PCM values for each channel
			handle_paula_channel_output(&audio_channels, frame);
		} else if (tdelta_control == 0x80) {
			// This frame is a register write or a loop event
			handle_paula_event(&audio_channels, wave_file, frame,
				settings);
		} else {
			fprintf(stderr, "Unsupoorted control byte: %u."
				"This is probably a bug or a format "
				"extension.\n", tdelta_control);
			abort();
		}
	}

	// Fix sizes in wave file header
	const size_t wave_size = ftell(wave_file);
	fseek(wave_file, 4, SEEK_SET);
	write_le32(wave_file, (uint32_t) wave_size - 8);
	fseek(wave_file, 40, SEEK_SET);
	write_le32(wave_file, (uint32_t) (wave_size - 44));

	fclose(reg_file);
	return 0;
}
