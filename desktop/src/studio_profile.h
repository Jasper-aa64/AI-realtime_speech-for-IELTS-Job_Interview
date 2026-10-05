#pragma once

class QObject;
class QWebEngineProfile;

namespace studio {

// One persistent profile for every window: cookies (login), localStorage and cache survive restarts.
QWebEngineProfile *createStudioProfile(QObject *parent);

} // namespace studio
