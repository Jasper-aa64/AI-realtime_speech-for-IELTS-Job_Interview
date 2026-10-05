#pragma once

#include <QUrl>
#include <QWidget>

class QLabel;

namespace studio {

// Shown instead of the web view when the server can't be reached.
class ErrorPage : public QWidget {
    Q_OBJECT
public:
    explicit ErrorPage(QWidget *parent = nullptr);

    void showFor(const QUrl &server, const QString &detail);
    QString detailText() const;

signals:
    void retryRequested();
    void changeServerRequested();

private:
    QLabel *m_detail = nullptr;
};

} // namespace studio
