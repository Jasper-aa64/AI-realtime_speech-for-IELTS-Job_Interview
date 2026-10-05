#include "error_page.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

namespace studio {

ErrorPage::ErrorPage(QWidget *parent) : QWidget(parent) {
    auto *title = new QLabel(QStringLiteral("连不上 IELTS Studio 服务器"), this);
    QFont titleFont = title->font();
    titleFont.setPointSizeF(titleFont.pointSizeF() * 1.6);
    titleFont.setWeight(QFont::Medium);
    title->setFont(titleFont);
    title->setAlignment(Qt::AlignCenter);

    m_detail = new QLabel(this);
    m_detail->setAlignment(Qt::AlignCenter);
    m_detail->setWordWrap(true);
    m_detail->setTextInteractionFlags(Qt::TextSelectableByMouse);
    m_detail->setForegroundRole(QPalette::PlaceholderText);

    auto *retry = new QPushButton(QStringLiteral("重试"), this);
    retry->setObjectName(QStringLiteral("retryButton"));
    retry->setDefault(true);
    auto *change = new QPushButton(QStringLiteral("更改服务器地址…"), this);
    change->setObjectName(QStringLiteral("changeServerButton"));
    connect(retry, &QPushButton::clicked, this, &ErrorPage::retryRequested);
    connect(change, &QPushButton::clicked, this, &ErrorPage::changeServerRequested);

    auto *buttons = new QHBoxLayout;
    buttons->addStretch();
    buttons->addWidget(change);
    buttons->addWidget(retry);
    buttons->addStretch();

    auto *layout = new QVBoxLayout(this);
    layout->addStretch();
    layout->addWidget(title);
    layout->addSpacing(8);
    layout->addWidget(m_detail);
    layout->addSpacing(20);
    layout->addLayout(buttons);
    layout->addStretch();
}

void ErrorPage::showFor(const QUrl &server, const QString &detail) {
    m_detail->setText(server.toString() + QStringLiteral(" · ") + detail);
}

QString ErrorPage::detailText() const {
    return m_detail->text();
}

} // namespace studio
