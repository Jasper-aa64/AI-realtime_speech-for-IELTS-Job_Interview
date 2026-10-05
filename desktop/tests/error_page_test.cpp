#include <QPushButton>
#include <QSignalSpy>
#include <QtTest>

#include "error_page.h"

class ErrorPageTest : public QObject {
    Q_OBJECT
private slots:
    void showsServerAndDetail() {
        studio::ErrorPage page;
        page.showFor(QUrl(QStringLiteral("https://studio.example.com/")), QStringLiteral("连接被拒绝"));
        QVERIFY(page.detailText().contains(QStringLiteral("https://studio.example.com/")));
        QVERIFY(page.detailText().contains(QStringLiteral("连接被拒绝")));
    }

    void buttonsEmitSignals() {
        studio::ErrorPage page;
        QSignalSpy retry(&page, &studio::ErrorPage::retryRequested);
        QSignalSpy change(&page, &studio::ErrorPage::changeServerRequested);

        auto *retryButton = page.findChild<QPushButton *>(QStringLiteral("retryButton"));
        auto *changeButton = page.findChild<QPushButton *>(QStringLiteral("changeServerButton"));
        QVERIFY(retryButton);
        QVERIFY(changeButton);
        QCOMPARE(retryButton->text(), QStringLiteral("重试"));

        QTest::mouseClick(retryButton, Qt::LeftButton);
        QTest::mouseClick(changeButton, Qt::LeftButton);
        QCOMPARE(retry.count(), 1);
        QCOMPARE(change.count(), 1);
    }
};

QTEST_MAIN(ErrorPageTest)
#include "error_page_test.moc"
