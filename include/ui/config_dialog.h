#pragma once 
 
#include <QtWidgets/QDialog> 
#include <QtWidgets/QWidget> 
#include <QtCore/QObject>
#include <QtWidgets/QLineEdit> 
#include <QtWidgets/QSpinBox> 
#include <QtWidgets/QCheckBox> 
#include <QtWidgets/QPushButton> 

namespace interview {
namespace ui {

class ConfigDialog : public QDialog {
    Q_OBJECT 

public:
    explicit ConfigDialog(QWidget *parent = nullptr);
    ~ConfigDialog();

    QString GetCandidateName() const; 
    QString GetResumePath() const; 
    int GetMinQuestions() const; 
    bool IsUseResume() const; 

private slots:
    void OnBrowseResume();
    void OnUseResumeToggled(bool checked);
    void OnAccepted();

private:
    void SetupUi();
    bool ValidateInput();
    
    QLineEdit* name_edit_;          
    QCheckBox* use_resume_check_;   
    QLineEdit* resume_edit_;        
    QPushButton* browse_button_;    
    QSpinBox* questions_spin_box_;  
    QPushButton* ok_button_;        
    QPushButton* cancel_button_;    
};

} // namespace ui
} // namespace interview

