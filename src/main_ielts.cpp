#include "ielts/ielts_manager.h"
#include "common/config.h"
#include "common/logger.h"
#include "services/realtime_client.h"
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <termios.h>
#include <unistd.h>

namespace {

std::unique_ptr<interview::services::RealtimeClient> g_client;

void SignalHandler(int signal) {
    std::cout << "\nReceived signal " << signal << ", shutting down...\n";
    if (g_client) {
        g_client->Close();
    }
    std::exit(0);
}

void PrintUsage() {
    std::cout
        << "Usage:\n"
        << "  IELTSSpeakingSimulator --config-file <path> [--data-dir data/ielts] [--reports-dir reports] [--debug]\n";
}

void PrintMenu() {
    std::cout
        << "\n\033[1;36mIELTS Speaking Simulator v1.0\033[0m\n"
        << "================================\n"
        << "[1] Full Mock Exam (P1 + P2 + P3)\n"
        << "[2] Practice Part 1 only\n"
        << "[3] Practice Part 2 only\n"
        << "[4] Practice Part 3 only\n"
        << "[5] View last report\n"
        << "[q] Quit\n"
        << "> ";
}

void PrintLastReport(const std::string& path) {
    if (path.empty()) {
        std::cout << "No report has been generated in this session.\n";
        return;
    }
    std::ifstream input(path);
    if (!input) {
        std::cout << "Could not open last report: " << path << "\n";
        return;
    }
    std::cout << "\n" << input.rdbuf() << "\n";
}

} // namespace

int main(int argc, char* argv[]) {
    std::string config_path;
    std::string data_dir = "data/ielts";
    std::string reports_dir = "reports";
    bool debug = false;

    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            auto next = [&](const std::string& name) {
                if (i + 1 >= argc) {
                    throw std::runtime_error("Missing value for argument: " + name);
                }
                return std::string(argv[++i]);
            };

            if (arg == "--config-file") {
                config_path = next(arg);
            } else if (arg == "--data-dir") {
                data_dir = next(arg);
            } else if (arg == "--reports-dir") {
                reports_dir = next(arg);
            } else if (arg == "--debug") {
                debug = true;
            } else if (arg == "-h" || arg == "--help") {
                PrintUsage();
                return 0;
            } else {
                throw std::runtime_error("Unknown argument: " + arg);
            }
        }

        if (config_path.empty()) {
            throw std::runtime_error("--config-file is required");
        }

        interview::common::Config::Instance().LoadFromFile(config_path);
        interview::common::Logger::Init("ielts.log", debug);

        auto& cfg = interview::common::Config::Instance();
        g_client = std::make_unique<interview::services::RealtimeClient>(cfg.ws_config.base_url, cfg.ws_config.headers);
        try {
            g_client->Connect();
        } catch (const std::exception& e) {
            LOG_WARNING("Realtime service unavailable; IELTS CLI will use transcript fallback: {}", e.what());
            std::cerr << "Realtime service unavailable; continuing with transcript fallback.\n";
        }

        std::signal(SIGINT, SignalHandler);
        std::signal(SIGTERM, SignalHandler);

        ielts::IELTSManager manager(data_dir, reports_dir, *g_client);

        while (true) {
            ::tcflush(STDIN_FILENO, TCIFLUSH);
            PrintMenu();
            std::string choice;
            std::getline(std::cin, choice);
            try {
                if (choice == "1") {
                    manager.RunExam(ielts::ExamMode::kFullExam);
                } else if (choice == "2") {
                    manager.RunExam(ielts::ExamMode::kPart1Only);
                } else if (choice == "3") {
                    manager.RunExam(ielts::ExamMode::kPart2Only);
                } else if (choice == "4") {
                    manager.RunExam(ielts::ExamMode::kPart3Only);
                } else if (choice == "5") {
                    PrintLastReport(manager.GetLastReportPath());
                } else if (choice == "q" || choice == "Q") {
                    break;
                } else {
                    std::cout << "Unknown menu option.\n";
                }
            } catch (const std::exception& e) {
                std::cerr << "IELTS session failed: " << e.what() << "\n";
            }
        }

        if (g_client->IsConnected()) {
            g_client->Close();
        }
        g_client.reset();
    } catch (const std::exception& e) {
        std::cerr << "Fatal error: " << e.what() << "\n";
        PrintUsage();
        return 1;
    }

    return 0;
}
