pragma ComponentBehavior: Bound
// qmllint disable missing-property stale-property-read

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Item {
    id: root

    readonly property var controller: AppController.articleVideo
    readonly property bool isBusy: controller ? controller.isBusy : false
    readonly property bool hasScenes: controller && controller.scenesCount > 0

    DefaultAudioOutput {
        id: articleVoiceAudioOutput
        volume: 1.0
    }

    MediaPlayer {
        id: articleVoicePlayer
        audioOutput: articleVoiceAudioOutput
        source: controller ? controller.voicePreviewSource : ""
        onMediaStatusChanged: function() {
            if (mediaStatus === MediaPlayer.EndOfMedia) {
                articleVoicePlayer.stop();
                if (controller) controller.setVoicePreviewPlaying(false);
            }
        }
        onPlaybackStateChanged: function() {
            if (controller) {
                controller.setVoicePreviewPlaying(playbackState === MediaPlayer.PlayingState);
            }
        }
    }

    DefaultAudioOutput {
        id: articleBgmAudioOutput
        volume: controller ? controller.bgmVolume : 0.15
    }

    MediaPlayer {
        id: articleBgmPlayer
        audioOutput: articleBgmAudioOutput
        source: controller ? controller.bgmPreviewSource : ""
        loops: MediaPlayer.Infinite
        onMediaStatusChanged: function() {
            if (mediaStatus === MediaPlayer.EndOfMedia) {
                articleBgmPlayer.stop();
                if (controller) controller.setBgmPreviewPlaying(false);
            }
        }
        onPlaybackStateChanged: function() {
            if (controller) {
                controller.setBgmPreviewPlaying(playbackState === MediaPlayer.PlayingState);
            }
        }
    }

    Component.onDestruction: {
        articleVoicePlayer.stop();
        articleBgmPlayer.stop();
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space12

        // --- Top Header ---
        PageHeader {
            Layout.fillWidth: true
            title: qsTr("Đọc truyện & Bài viết AI (1080p)")

            RowLayout {
                spacing: Theme.space8

                StudioButton {
                    text: qsTr("Nhập tệp .txt")
                    iconGlyph: "\uE8E5"
                    compact: true
                    enabled: !root.isBusy
                    onClicked: controller.pickArticleTextFile()
                }

                StudioButton {
                    text: qsTr("Làm mới")
                    iconGlyph: "\uE72C"
                    compact: true
                    enabled: !root.isBusy
                    onClicked: controller.resetProject()
                }
            }
        }

        // --- Progress & Status Banner ---
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: bannerContent.implicitHeight + Theme.space8 * 2
            visible: Boolean(controller && (controller.progressMessage || controller.status === "error" || controller.status === "done"))
            radius: Theme.radiusSmall
            color: controller && controller.status === "error" ? Theme.dangerSubtle
                : controller && controller.status === "done" ? Theme.successSubtle
                : Theme.interactiveSubtle
            border.width: 1
            border.color: controller && controller.status === "error" ? Theme.danger
                : controller && controller.status === "done" ? Theme.success
                : Theme.interactive

            RowLayout {
                id: bannerContent
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space12

                FluentIcon {
                    name: controller && controller.status === "error" ? "error"
                        : controller && controller.status === "done" ? "success"
                        : "info"
                    iconSize: 20
                    iconColor: controller && controller.status === "error" ? Theme.danger
                        : controller && controller.status === "done" ? Theme.success
                        : Theme.interactive
                }

                Text {
                    Layout.fillWidth: true
                    text: controller ? (controller.status === "error" ? controller.lastErrorMessage : controller.progressMessage) : ""
                    color: controller && controller.status === "error" ? "#FFDAD6" : Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    visible: Boolean(controller && controller.status === "done" && controller.outputVideoPath)
                    spacing: Theme.space8

                    StudioButton {
                        text: qsTr("Mở video")
                        tone: "secondary"
                        compact: true
                        onClicked: controller.openOutputVideo()
                    }

                    StudioButton {
                        text: qsTr("Mở thư mục")
                        compact: true
                        onClicked: controller.openOutputFolder()
                    }

                    StudioButton {
                        text: (controller && controller.aspectRatio === "9:16") ? qsTr("Đăng YouTube Shorts") : qsTr("Đăng YouTube")
                        iconGlyph: "\uE714"
                        tone: "primary"
                        compact: true
                        onClicked: youtubePublishDialog.openForCurrentProject()
                    }
                }
            }
        }

        AppProgressBar {
            Layout.fillWidth: true
            visible: root.isBusy
            value: controller ? controller.progressPercent : 0
            indeterminate: Boolean(root.isBusy && controller && controller.progressPercent <= 10)
        }

        // --- Main 3-Column Content Layout ---
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space12

            // =================================================================
            // CỘT 1: Nhập bài viết & Chọn nhân vật 2D
            // =================================================================
            Rectangle {
                Layout.preferredWidth: 380
                Layout.minimumWidth: 320
                Layout.fillHeight: true
                radius: Theme.radiusSmall
                color: Theme.surface
                border.width: 1
                border.color: Theme.divider

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space8

                    Text {
                        text: qsTr("1. Kịch bản & Nhân vật 2D")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.section
                        font.weight: Font.Bold
                    }

                    Text {
                        text: qsTr("Nội dung bài viết:")
                        color: Theme.textMuted
                        font.pixelSize: TypeScale.label
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 140
                        clip: true

                        AppTextArea {
                            id: articleTextArea
                            text: controller ? controller.articleText : ""
                            placeholderText: qsTr("Dán hoặc gõ nội dung bài viết, câu chuyện cần làm video tại đây...")
                            onTextChanged: {
                                if (controller && controller.articleText !== text) {
                                    controller.setArticleText(text);
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    // Character selector section
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Chân dung nhân vật (Tùy chọn):")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }
                        StudioButton {
                            text: qsTr("Xóa tất cả")
                            compact: true
                            tone: "danger"
                            visible: controller && controller.characters && controller.characters.length > 0
                            onClicked: if (controller) controller.deleteAllCharacters()
                        }
                        StudioButton {
                            text: qsTr("Khôi phục mẫu")
                            compact: true
                            tone: "tertiary"
                            onClicked: if (controller) controller.restoreDefaultCharacters()
                        }
                        StudioButton {
                            text: qsTr("Nhập ảnh...")
                            compact: true
                            tone: "secondary"
                            onClicked: if (controller) controller.pickAndImportCharacterSheet()
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 160
                        clip: true

                        ListView {
                            id: characterListView
                            orientation: ListView.Horizontal
                            spacing: Theme.space8
                            model: controller ? controller.characters : []

                            header: Item {
                                width: 125 + Theme.space8
                                height: 150

                                Rectangle {
                                    id: freeModeCard
                                    width: 125
                                    height: 150
                                    radius: Theme.radiusSmall
                                    property bool isSelected: !controller || controller.selectedCharacterId === "none" || controller.selectedCharacterId === ""
                                    color: isSelected ? Theme.interactiveSubtle : Theme.surfaceStrong
                                    border.width: isSelected ? 2 : 1
                                    border.color: isSelected ? Theme.interactive : Theme.outline

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 4

                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 92
                                            radius: Theme.radiusSmall
                                            color: Theme.surfaceMuted

                                            ColumnLayout {
                                                anchors.centerIn: parent
                                                spacing: 4
                                                FluentIcon {
                                                    Layout.alignment: Qt.AlignHCenter
                                                    name: "sparkle"
                                                    iconColor: freeModeCard.isSelected ? Theme.interactive : Theme.textMuted
                                                }
                                                Text {
                                                    Layout.alignment: Qt.AlignHCenter
                                                    text: qsTr("Tự do")
                                                    color: freeModeCard.isSelected ? Theme.interactive : Theme.textMuted
                                                    font.family: Theme.fontFamily
                                                    font.pixelSize: 11
                                                    font.weight: Font.DemiBold
                                                }
                                            }
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: qsTr("Không dùng mẫu")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: qsTr("Theo ngữ cảnh truyện")
                                            color: Theme.textMuted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: 9
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: if (controller) controller.selectCharacter("none")
                                    }
                                }
                            }

                            delegate: Rectangle {
                                id: charCard
                                required property var modelData
                                required property int index

                                width: 125
                                height: 150
                                radius: Theme.radiusSmall
                                color: controller && controller.selectedCharacterId === charCard.modelData.id ? Theme.interactiveSubtle : Theme.surfaceStrong
                                border.width: controller && controller.selectedCharacterId === charCard.modelData.id ? 2 : 1
                                border.color: controller && controller.selectedCharacterId === charCard.modelData.id ? Theme.interactive : Theme.outline

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 4

                                    Image {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 92
                                        Layout.alignment: Qt.AlignHCenter
                                        source: charCard.modelData.thumbnail ? "file:///" + charCard.modelData.thumbnail.replace(/\\/g, "/") : ""
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        clip: true

                                        Rectangle {
                                            anchors.fill: parent
                                            color: Theme.surfaceMuted
                                            visible: parent.status !== Image.Ready
                                            FluentIcon {
                                                anchors.centerIn: parent
                                                name: "person"
                                                iconColor: Theme.textMuted
                                            }
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: charCard.modelData.name || ""
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: charCard.modelData.age_group || ""
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 9
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: controller.selectCharacter(charCard.modelData.id)
                                }

                                // Delete button for individual character card
                                Rectangle {
                                    id: deleteBtn
                                    anchors.top: parent.top
                                    anchors.right: parent.right
                                    anchors.margins: 4
                                    width: 20
                                    height: 20
                                    radius: 10
                                    z: 10
                                    color: deleteMouse.containsMouse ? Theme.danger : Theme.surface
                                    border.color: deleteMouse.containsMouse ? Theme.danger : Theme.outline
                                    border.width: 1

                                    Text {
                                        anchors.centerIn: parent
                                        text: "\uE711"
                                        font.family: "Segoe MDL2 Assets"
                                        font.pixelSize: 9
                                        color: deleteMouse.containsMouse ? "#ffffff" : Theme.textMuted
                                    }

                                    MouseArea {
                                        id: deleteMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            if (controller) {
                                                controller.deleteCharacter(charCard.modelData.id)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Status helper for character selection
                    Text {
                        Layout.fillWidth: true
                        text: (!controller || controller.selectedCharacterId === "none" || controller.selectedCharacterId === "")
                              ? qsTr("✨ Đang bật: Tự do sáng tạo — AI sẽ tạo hình ảnh & nhân vật mới tự nhiên theo câu chuyện, không bị áp đặt chân dung cũ.")
                              : qsTr("🎯 Đang khóa mẫu nhân vật: AI sẽ dùng ảnh mẫu được chọn để đồng bộ diện mạo xuyên suốt video.")
                        color: (!controller || controller.selectedCharacterId === "none" || controller.selectedCharacterId === "")
                               ? Theme.success
                               : Theme.interactive
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }

                    // Target image count
                    Text {
                        text: qsTr("Số lượng ảnh minh họa AI:")
                        color: Theme.textMuted
                        font.pixelSize: TypeScale.label
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Repeater {
                            model: [
                                { label: qsTr("1 ảnh"), count: 1 },
                                { label: qsTr("3 ảnh"), count: 3 },
                                { label: qsTr("5 ảnh"), count: 5 },
                                { label: qsTr("10 ảnh"), count: 10 }
                            ]

                            delegate: StudioButton {
                                id: countBtn
                                required property var modelData
                                Layout.fillWidth: true
                                text: countBtn.modelData.label
                                compact: true
                                tone: controller && controller.imageCountTarget === countBtn.modelData.count ? "primary" : "secondary"
                                onClicked: controller.setImageCountTarget(countBtn.modelData.count)
                            }
                        }
                    }
                }
            }

            // =================================================================
            // CỘT 2: Cấu hình giọng đọc & Phong cách
            // =================================================================
            Rectangle {
                Layout.preferredWidth: 320
                Layout.minimumWidth: 280
                Layout.fillHeight: true
                radius: Theme.radiusSmall
                color: Theme.surface
                border.width: 1
                border.color: Theme.divider

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: Theme.space12

                        Text {
                            text: qsTr("2. Giọng đọc & Phong cách")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.section
                            font.weight: Font.Bold
                        }

                        // TTS Provider
                        Text {
                            text: qsTr("Bộ đọc giọng (TTS):")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }

                        SegmentedControl {
                            Layout.fillWidth: true
                            options: [
                                { label: qsTr("Edge-TTS (Online - Chuẩn)"), value: "edge" },
                                { label: qsTr("VieNeu (Offline)"), value: "vieneu" }
                            ]
                            currentValue: controller ? controller.ttsProvider : "edge"
                            onActivated: function(val) { controller.setTtsProvider(val); }
                        }

                        // Voice Selector
                        Text {
                            text: qsTr("Giọng đọc tiếng Việt:")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }

                        AppComboBox {
                            Layout.fillWidth: true
                            model: [
                                "edge:vi-VN-NamMinhNeural (Nam phát thanh chuẩn)",
                                "edge:vi-VN-HoaiMyNeural (Nữ truyền cảm chuẩn)",
                                "vieneu:Hải Đăng (Nam trầm ấm - Offline)"
                            ]
                            currentIndex: {
                                const voices = [
                                    "vi-VN-NamMinhNeural",
                                    "vi-VN-HoaiMyNeural",
                                    "vieneu:Hải Đăng"
                                ];
                                const idx = voices.indexOf(controller ? controller.ttsVoice : "vi-VN-NamMinhNeural");
                                return idx >= 0 ? idx : 0;
                            }
                            onActivated: function(index) {
                                const voices = [
                                    "vi-VN-NamMinhNeural",
                                    "vi-VN-HoaiMyNeural",
                                    "vieneu:Hải Đăng"
                                ];
                                controller.setTtsVoice(voices[index]);
                            }
                        }

                        // Voice Preview Button & Status
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            StudioButton {
                                text: controller && controller.isVoicePreviewPlaying ? qsTr("Dừng nghe") : qsTr("Nghe thử giọng")
                                iconGlyph: controller && controller.isVoicePreviewPlaying ? "\uE71A" : "\uE768"
                                compact: true
                                tone: controller && controller.isVoicePreviewPlaying ? "danger" : "secondary"
                                onClicked: {
                                    if (!controller) return;
                                    if (controller.isVoicePreviewPlaying) {
                                        articleVoicePlayer.stop();
                                        controller.stopVoicePreview();
                                    } else {
                                        if (articleBgmPlayer.playbackState === MediaPlayer.PlayingState) {
                                            articleBgmPlayer.stop();
                                            controller.stopBgmPreview();
                                        }
                                        const url = controller.previewVoice();
                                        if (url) {
                                            articleVoicePlayer.source = url;
                                            articleVoicePlayer.play();
                                        }
                                    }
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: controller ? controller.voicePreviewStatus : ""
                                color: Theme.interactive
                                font.pixelSize: Theme.caption
                                elide: Text.ElideRight
                                visible: text.length > 0
                            }
                        }

                        // Reading Speed
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: qsTr("Tốc độ đọc:")
                                color: Theme.textMuted
                                font.pixelSize: TypeScale.label
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: (controller ? controller.ttsSpeed.toFixed(1) : "1.0") + "x"
                                color: Theme.text
                                font.weight: Font.DemiBold
                            }
                        }

                        AppSlider {
                            Layout.fillWidth: true
                            from: 0.5
                            to: 2.0
                            stepSize: 0.1
                            value: controller ? controller.ttsSpeed : 1.0
                            onMoved: controller.setTtsSpeed(value)
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.divider
                        }

                        // Aspect Ratio
                        Text {
                            text: qsTr("Tỷ lệ khung hình video:")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }

                        SegmentedControl {
                            Layout.fillWidth: true
                            options: [
                                { label: qsTr("16:9 (YouTube)"), value: "16:9" },
                                { label: qsTr("9:16 (Shorts)"), value: "9:16" }
                            ]
                            currentValue: controller ? controller.aspectRatio : "16:9"
                            onActivated: function(val) { controller.setAspectRatio(val); }
                        }

                        // Image Style
                        Text {
                            text: qsTr("Phong cách hình ảnh AI:")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }

                        AppComboBox {
                            Layout.fillWidth: true
                            model: [
                                qsTr("Anime 2D (Makoto Shinkai)"),
                                qsTr("Manhwa Webtoon"),
                                qsTr("Tranh thủy mặc (Watercolor)"),
                                qsTr("Cyberpunk Neon"),
                                qsTr("Western Comic"),
                                qsTr("Cinematic Film")
                            ]
                            currentIndex: {
                                const styles = [
                                    "anime_2d",
                                    "manhwa_webtoon",
                                    "watercolor",
                                    "cyberpunk",
                                    "comic_book",
                                    "cinematic"
                                ];
                                const idx = styles.indexOf(controller ? controller.imageStyle : "anime_2d");
                                return idx >= 0 ? idx : 0;
                            }
                            onActivated: function(index) {
                                const styles = [
                                    "anime_2d",
                                    "manhwa_webtoon",
                                    "watercolor",
                                    "cyberpunk",
                                    "comic_book",
                                    "cinematic"
                                ];
                                controller.setImageStyle(styles[index]);
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.divider
                        }

                        // AI Engine & API Key Setup
                        Text {
                            text: qsTr("Động cơ tạo ảnh AI:")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.label
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: engineLayout.implicitHeight + Theme.space12 * 2
                            radius: Theme.radiusSmall
                            color: controller && controller.hasGoogleApiKey ? Theme.surfaceSubtle : Theme.interactiveSubtle
                            border.width: 1
                            border.color: controller && controller.hasGoogleApiKey ? Theme.outline : Theme.interactive

                            ColumnLayout {
                                id: engineLayout
                                anchors.fill: parent
                                anchors.margins: Theme.space12
                                spacing: Theme.space8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space8

                                    FluentIcon {
                                        name: controller && controller.hasGoogleApiKey ? "sparkle" : "info"
                                        iconColor: controller && controller.hasGoogleApiKey ? Theme.accent : Theme.interactive
                                        iconSize: 18
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2

                                        Text {
                                            Layout.fillWidth: true
                                            text: controller ? controller.activeAiEngineName : qsTr("Cổng AI Trực tuyến Miễn phí (Pollinations)")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: TypeScale.control
                                            font.weight: Font.DemiBold
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: controller ? controller.activeAiEngineSubtitle : qsTr("Miễn phí 100%, tự động tạo ảnh thuần Việt sắc nét.")
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.caption
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space8

                                    StudioButton {
                                        Layout.fillWidth: true
                                        text: qsTr("Cài đặt Cổng Tạo Ảnh AI…")
                                        iconGlyph: "\uE8D7"
                                        compact: true
                                        tone: controller && (controller.hasGoogleApiKey || controller.hasPollenKey) ? "secondary" : "primary"
                                        onClicked: apiKeyDialog.open()
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.divider
                        }

                        // Background Music
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: qsTr("Nhạc nền (BGM):")
                                color: Theme.textMuted
                                font.pixelSize: TypeScale.label
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: controller ? controller.bgmFileName : qsTr("Mặc định")
                                color: Theme.interactive
                                font.pixelSize: TypeScale.caption
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                                Layout.maximumWidth: 160
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            StudioButton {
                                Layout.fillWidth: true
                                text: qsTr("Chọn tệp…")
                                iconGlyph: "\uE8D6"
                                compact: true
                                toolTipText: controller && controller.bgmPath ? controller.bgmPath : qsTr("Chọn tệp nhạc nền từ máy tính")
                                onClicked: controller.pickBgmFile()
                            }

                            StudioButton {
                                text: qsTr("Mặc định")
                                compact: true
                                tone: (!controller || !controller.bgmPath || controller.bgmPath === "default") ? "primary" : "secondary"
                                toolTipText: qsTr("Dùng nhạc nền có sẵn được tối ưu")
                                onClicked: {
                                    if (articleBgmPlayer.playbackState === MediaPlayer.PlayingState) {
                                        articleBgmPlayer.stop();
                                    }
                                    if (controller) controller.setDefaultBgm();
                                }
                            }

                            StudioButton {
                                text: controller && controller.isBgmPreviewPlaying ? qsTr("Dừng") : qsTr("Nghe thử")
                                iconGlyph: controller && controller.isBgmPreviewPlaying ? "\uE71A" : "\uE768"
                                compact: true
                                tone: controller && controller.isBgmPreviewPlaying ? "danger" : "secondary"
                                toolTipText: controller && controller.isBgmPreviewPlaying ? qsTr("Dừng nghe thử nhạc nền") : qsTr("Nghe thử nhạc nền hiện tại")
                                onClicked: {
                                    if (!controller) return;
                                    if (controller.isBgmPreviewPlaying) {
                                        articleBgmPlayer.stop();
                                        controller.stopBgmPreview();
                                    } else {
                                        if (articleVoicePlayer.playbackState === MediaPlayer.PlayingState) {
                                            articleVoicePlayer.stop();
                                            controller.stopVoicePreview();
                                        }
                                        const url = controller.previewBgm();
                                        if (url) {
                                            articleBgmPlayer.source = url;
                                            articleBgmPlayer.play();
                                        }
                                    }
                                }
                            }

                            StudioButton {
                                iconGlyph: "\uE711"
                                compact: true
                                tone: (controller && controller.bgmPath === "none") ? "danger" : "secondary"
                                toolTipText: qsTr("Tắt nhạc nền")
                                onClicked: {
                                    articleBgmPlayer.stop();
                                    if (controller) controller.disableBgm();
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: controller ? controller.bgmPreviewStatus : ""
                            color: Theme.interactive
                            font.pixelSize: Theme.caption
                            elide: Text.ElideRight
                            visible: text.length > 0
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: qsTr("Âm lượng nhạc nền (Ducking):")
                                color: Theme.textMuted
                                font.pixelSize: TypeScale.label
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: Math.round((controller ? controller.bgmVolume : 0.15) * 100) + "%"
                                color: Theme.text
                                font.weight: Font.DemiBold
                            }
                        }

                        AppSlider {
                            Layout.fillWidth: true
                            from: 0.0
                            to: 0.5
                            stepSize: 0.01
                            value: controller ? controller.bgmVolume : 0.15
                            onMoved: controller.setBgmVolume(value)
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.divider
                        }

                        // Explicit Save / Confirm Settings Button
                        StudioButton {
                            Layout.fillWidth: true
                            text: qsTr("Lưu & Áp Dụng Cấu Hình")
                            iconGlyph: "\uE74E"
                            tone: "primary"
                            toolTipText: qsTr("Xác nhận và lưu cấu hình tỷ lệ khung hình, giọng đọc và phong cách trước khi tạo ảnh hoặc xuất video")
                            onClicked: {
                                if (controller) {
                                    controller.saveConfig();
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: controller ? controller.configSavedMessage : ""
                            color: Theme.accent
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            visible: text.length > 0
                        }
                    }
                }
            }

            // =================================================================
            // CỘT 3: Xem trước phân cảnh & Xuất Video
            // =================================================================
            Rectangle {
                Layout.fillWidth: true
                Layout.minimumWidth: 360
                Layout.fillHeight: true
                radius: Theme.radiusSmall
                color: Theme.surface
                border.width: 1
                border.color: Theme.divider

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space8

                    // Header & Action buttons
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Text {
                            text: root.hasScenes
                                ? qsTr("3. Phân cảnh kịch bản (%1 cảnh)").arg(controller.scenesCount)
                                : qsTr("3. Xem trước & Xuất Video")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.section
                            font.weight: Font.Bold
                        }

                        Item { Layout.fillWidth: true }

                        StudioButton {
                            text: qsTr("Phân tích kịch bản")
                            iconGlyph: "\uE890"
                            enabled: !root.isBusy && Boolean(controller && controller.articleText.trim().length > 0)
                            compact: true
                            onClicked: controller.analyzeStory()
                        }

                        StudioButton {
                            text: qsTr("Tạo ảnh AI")
                            iconGlyph: "\uEB9F"
                            enabled: !root.isBusy && root.hasScenes
                            compact: true
                            onClicked: controller.generateImages()
                        }

                        StudioButton {
                            text: qsTr("Xuất Video 1080p")
                            iconGlyph: "\uE714"
                            tone: "primary"
                            enabled: !root.isBusy && root.hasScenes
                            compact: true
                            onClicked: controller.renderVideo()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    // Empty state when no scenes
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: !root.hasScenes

                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: Theme.space12

                            FluentIcon {
                                Layout.alignment: Qt.AlignHCenter
                                name: "video"
                                iconSize: 48
                                iconColor: Theme.textMuted
                            }

                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: qsTr("Chưa có phân cảnh nào")
                                color: Theme.text
                                font.pixelSize: TypeScale.section
                                font.weight: Font.DemiBold
                            }

                            Text {
                                Layout.maximumWidth: 320
                                Layout.alignment: Qt.AlignHCenter
                                text: qsTr("Dán nội dung bài viết ở Cột 1 và bấm 'Phân tích kịch bản' để AI chia đoạn và tạo hiệu ứng.")
                                color: Theme.textMuted
                                font.pixelSize: TypeScale.control
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    // Scenes list
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.hasScenes
                        clip: true

                        ListView {
                            id: scenesListView
                            spacing: Theme.space8
                            model: controller ? controller.scenes : []

                            delegate: Rectangle {
                                id: sceneCard
                                required property var modelData
                                required property int index

                                width: scenesListView.width - 12
                                implicitHeight: sceneCardContent.implicitHeight + Theme.space12 * 2
                                radius: Theme.radiusSmall
                                color: Theme.surfaceStrong
                                border.width: 1
                                border.color: sceneCard.modelData.has_image ? Theme.interactiveSubtle : Theme.outline

                                ColumnLayout {
                                    id: sceneCardContent
                                    anchors.fill: parent
                                    anchors.margins: Theme.space12
                                    spacing: Theme.space8

                                    // Scene header row
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        Rectangle {
                                            Layout.preferredWidth: 24
                                            Layout.preferredHeight: 24
                                            radius: 12
                                            color: Theme.interactive
                                            Text {
                                                anchors.centerIn: parent
                                                text: String(sceneCard.index + 1)
                                                color: Theme.textOnAccent
                                                font.pixelSize: 11
                                                font.weight: Font.Bold
                                            }
                                        }

                                        Text {
                                            text: qsTr("Thời lượng: ~%1s").arg(sceneCard.modelData.duration_sec ? sceneCard.modelData.duration_sec.toFixed(1) : "3.0")
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.label
                                        }

                                        Item { Layout.fillWidth: true }

                                        // Climax score badge
                                        Rectangle {
                                            radius: Theme.radiusTiny
                                            color: sceneCard.modelData.has_image ? Theme.interactiveSubtle : Theme.surfaceMuted
                                            Layout.preferredHeight: 20
                                            Layout.preferredWidth: scoreText.implicitWidth + 12

                                            Text {
                                                id: scoreText
                                                anchors.centerIn: parent
                                                text: sceneCard.modelData.has_image
                                                    ? qsTr("⭐ Trọng tâm (Điểm: %1)").arg(sceneCard.modelData.visual_priority_score ? sceneCard.modelData.visual_priority_score.toFixed(1) : "5.0")
                                                    : qsTr("Chuyển tiếp")
                                                color: sceneCard.modelData.has_image ? Theme.interactive : Theme.textMuted
                                                font.pixelSize: 10
                                                font.weight: Font.Medium
                                            }
                                        }
                                    }

                                    // Narration text
                                    Text {
                                        Layout.fillWidth: true
                                        text: sceneCard.modelData.text || ""
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: TypeScale.control
                                        wrapMode: Text.Wrap
                                    }

                                    // Visual context / AI prompt badge
                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: promptCol.implicitHeight + Theme.space8 * 2
                                        radius: Theme.radiusTiny
                                        color: Theme.surfaceSubtle
                                        border.width: 1
                                        border.color: Theme.borderSubtle
                                        visible: Boolean(sceneCard.modelData.has_image && sceneCard.modelData.image_prompt)

                                        ColumnLayout {
                                            id: promptCol
                                            anchors.fill: parent
                                            anchors.margins: Theme.space8
                                            spacing: 2

                                            Text {
                                                text: qsTr("🎬 Ngữ cảnh tạo ảnh AI:")
                                                color: Theme.interactive
                                                font.pixelSize: 10
                                                font.weight: Font.DemiBold
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                text: sceneCard.modelData.image_prompt || ""
                                                color: Theme.textMuted
                                                font.pixelSize: 11
                                                wrapMode: Text.Wrap
                                                maximumLineCount: 3
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }

                                    // Visual depiction / Image section
                                    Item {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: sceneCard.modelData.has_image_file ? 180 : 40

                                        // When image file is available
                                        RowLayout {
                                            anchors.fill: parent
                                            visible: Boolean(sceneCard.modelData.has_image_file)
                                            spacing: Theme.space12

                                            Image {
                                                Layout.preferredWidth: 240
                                                Layout.fillHeight: true
                                                source: sceneCard.modelData.image_path ? "file:///" + sceneCard.modelData.image_path.replace(/\\/g, "/") : ""
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: Theme.space8

                                                Text {
                                                    text: qsTr("Hiệu ứng: Ken Burns Zoom & Pan")
                                                    color: Theme.textMuted
                                                    font.pixelSize: TypeScale.label
                                                }

                                                StudioButton {
                                                    text: qsTr("Tạo lại ảnh này")
                                                    iconGlyph: "\uE72C"
                                                    compact: true
                                                    enabled: !root.isBusy
                                                    onClicked: regenImageDialog.openForScene(sceneCard.index, sceneCard.modelData.image_prompt || sceneCard.modelData.text)
                                                }

                                                StudioButton {
                                                    text: qsTr("Thay ảnh từ máy…")
                                                    iconGlyph: "\uEB9F"
                                                    compact: true
                                                    enabled: !root.isBusy
                                                    onClicked: controller.pickSceneImage(sceneCard.index)
                                                }
                                            }
                                        }

                                        // When image is not generated yet or uses predecessor
                                        Rectangle {
                                            anchors.fill: parent
                                            visible: !Boolean(sceneCard.modelData.has_image_file)
                                            radius: Theme.radiusTiny
                                            color: Theme.surfaceMuted
                                            border.width: 1
                                            border.color: Theme.outline

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 8
                                                spacing: 8

                                                FluentIcon {
                                                    name: sceneCard.modelData.has_image ? "image" : "play"
                                                    iconSize: 16
                                                    iconColor: Theme.textMuted
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: sceneCard.modelData.has_image
                                                        ? qsTr("Chờ sinh ảnh AI: %1").arg(sceneCard.modelData.image_prompt || sceneCard.modelData.text)
                                                        : qsTr("Dùng chung ảnh minh họa từ phân cảnh trước với camera tiếp diễn.")
                                                    color: Theme.textMuted
                                                    font.pixelSize: Theme.caption
                                                    elide: Text.ElideRight
                                                }

                                                StudioButton {
                                                    visible: Boolean(sceneCard.modelData.has_image)
                                                    text: qsTr("Tạo ảnh ngay")
                                                    compact: true
                                                    enabled: !root.isBusy
                                                    onClicked: regenImageDialog.openForScene(sceneCard.index, sceneCard.modelData.image_prompt || sceneCard.modelData.text)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // --- Xuất bản YouTube / YouTube Shorts ---
                    Rectangle {
                        Layout.fillWidth: true
                        visible: Boolean(controller && controller.outputVideoPath)
                        radius: Theme.radiusSmall
                        color: Theme.surfaceMuted
                        border.width: 1
                        border.color: controller && controller.youtubeConnected ? Theme.successSubtle : Theme.outline
                        implicitHeight: ytCardCol.implicitHeight + Theme.space12 * 2

                        ColumnLayout {
                            id: ytCardCol
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: Theme.space8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space8

                                PlatformLogo {
                                    platform: "youtube"
                                    Layout.preferredWidth: 20
                                    Layout.preferredHeight: 20
                                }

                                Text {
                                    text: (controller && controller.aspectRatio === "9:16")
                                        ? qsTr("Xuất bản lên YouTube Shorts")
                                        : qsTr("Xuất bản lên YouTube")
                                    color: Theme.text
                                    font.pixelSize: TypeScale.control
                                    font.weight: Font.Bold
                                }

                                Item { Layout.fillWidth: true }

                                StatusPill {
                                    status: controller && controller.youtubeConnected ? "success" : "ready"
                                    label: controller && controller.youtubeConnected
                                        ? (controller.youtubeChannelTitle ? qsTr("Kênh: %1").arg(controller.youtubeChannelTitle) : qsTr("Đã kết nối"))
                                        : qsTr("Chưa kết nối")
                                }
                            }

                            // When connected
                            ColumnLayout {
                                Layout.fillWidth: true
                                visible: Boolean(controller && controller.youtubeConnected)
                                spacing: Theme.space8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space8

                                    StudioButton {
                                        Layout.fillWidth: true
                                        text: (controller && controller.aspectRatio === "9:16")
                                            ? qsTr("Đăng ngay lên YouTube Shorts")
                                            : qsTr("Đăng ngay lên YouTube")
                                        iconGlyph: "\uE714"
                                        tone: "primary"
                                        compact: true
                                        enabled: Boolean(controller && !controller.isUploadingYoutube && controller.outputVideoPath)
                                        onClicked: {
                                            if (controller) controller.uploadToYouTube();
                                        }
                                    }

                                    StudioButton {
                                        text: qsTr("Tùy chỉnh tiêu đề & Đăng…")
                                        compact: true
                                        enabled: Boolean(controller && !controller.isUploadingYoutube && controller.outputVideoPath)
                                        onClicked: youtubePublishDialog.openForCurrentProject()
                                    }
                                }

                                AppProgressBar {
                                    Layout.fillWidth: true
                                    visible: Boolean(controller && controller.isUploadingYoutube)
                                    value: controller ? controller.youtubeUploadProgress : 0
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: controller ? controller.youtubeUploadMessage : ""
                                    color: controller && controller.youtubeVideoUrl ? Theme.success : Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    visible: text.length > 0
                                    wrapMode: Text.Wrap
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    visible: Boolean(controller && controller.youtubeVideoUrl)

                                    StudioButton {
                                        text: qsTr("Mở xem trên YouTube")
                                        iconGlyph: "\uE8A7"
                                        tone: "primary"
                                        compact: true
                                        onClicked: if (controller) controller.openYouTubeVideo()
                                    }
                                }
                            }

                            // When not connected
                            RowLayout {
                                Layout.fillWidth: true
                                visible: Boolean(!controller || !controller.youtubeConnected)
                                spacing: Theme.space8

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("Kết nối tài khoản Google YouTube của bạn một lần để đăng trực tiếp miễn phí.")
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    wrapMode: Text.Wrap
                                }

                                StudioButton {
                                    text: qsTr("Kết nối YouTube")
                                    iconGlyph: "\uE71B"
                                    compact: true
                                    tone: "primary"
                                    onClicked: if (controller) controller.connectYouTube()
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    AppDialog {
        id: apiKeyDialog
        title: qsTr("Cấu hình Cổng Tạo Ảnh AI")
        preferredWidth: 480

        ColumnLayout {
            spacing: Theme.space12
            width: parent.width

            Text {
                Layout.fillWidth: true
                text: qsTr("1. Cổng AI Miễn phí (Pollinations): Tự động tạo ảnh thuần Việt theo ngữ cảnh kịch bản. Máy chủ công cộng yêu cầu giãn cách 45 giây giữa các ảnh. Hệ thống sẽ tự động xếp hàng và tạo ảnh sắc nét cho từng cảnh.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
                wrapMode: Text.WordWrap
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("2. Pollen Key (Tùy chọn - Nhận miễn phí tại enter.pollinations.ai):")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.control
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Đăng nhập GitHub hoặc Google tại enter.pollinations.ai để nhận key miễn phí, giúp tạo ảnh liên tục siêu tốc mà không phải chờ giãn cách 45s.")
                color: Theme.textMuted
                font.pixelSize: TypeScale.caption
                wrapMode: Text.WordWrap
            }

            AppTextField {
                id: pollenKeyInput
                Layout.fillWidth: true
                placeholderText: controller && controller.hasPollenKey ? qsTr("Đã cấu hình: %1").arg(controller.pollenKeyMasked) : qsTr("Dán Pollen Key (pk_...) vào đây")
                echoMode: TextInput.PasswordEchoOnEdit
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                StudioButton {
                    text: qsTr("Lưu Pollen Key")
                    compact: true
                    tone: "primary"
                    enabled: pollenKeyInput.text.trim().length > 0
                    onClicked: {
                        if (controller.savePollenKey(pollenKeyInput.text.trim())) {
                            pollenKeyInput.text = "";
                        }
                    }
                }

                StudioButton {
                    visible: Boolean(controller && controller.hasPollenKey)
                    text: qsTr("Xóa Pollen Key")
                    compact: true
                    tone: "danger"
                    onClicked: controller.clearPollenKey()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("3. Google Gemini API Key (Dùng cho Kịch bản & Dịch thuật):")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.control
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Khóa Google AI Studio (miễn phí) dùng cho Phân tích kịch bản và Dịch thuật ngữ cảnh. (Lưu ý: Tạo ảnh Imagen 3 trực tiếp từ Google yêu cầu bật Billing trên Google Cloud).")
                color: Theme.textMuted
                font.pixelSize: TypeScale.caption
                wrapMode: Text.WordWrap
            }

            AppTextField {
                id: apiKeyInput
                Layout.fillWidth: true
                placeholderText: controller && controller.hasGoogleApiKey ? qsTr("Đã cấu hình: %1").arg(controller.googleApiKeyMasked) : qsTr("Dán API Key (AIzaSy...) vào đây")
                echoMode: TextInput.PasswordEchoOnEdit
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                StudioButton {
                    text: qsTr("Lưu Google Key")
                    compact: true
                    tone: "primary"
                    enabled: apiKeyInput.text.trim().length > 0
                    onClicked: {
                        if (controller.saveGoogleApiKey(apiKeyInput.text.trim())) {
                            apiKeyInput.text = "";
                        }
                    }
                }

                StudioButton {
                    visible: Boolean(controller && controller.hasGoogleApiKey)
                    text: qsTr("Xóa Google Key")
                    compact: true
                    tone: "danger"
                    onClicked: controller.clearGoogleApiKey()
                }
            }
        }

        footerActions: [
            StudioButton {
                text: qsTr("Đóng")
                compact: true
                onClicked: apiKeyDialog.close()
            }
        ]
    }

    AppDialog {
        id: regenImageDialog
        title: qsTr("Tùy chỉnh & Tạo lại ảnh (Cảnh %1)").arg(targetSceneIndex + 1)
        subtitle: qsTr("Bổ sung chỉ dẫn hoặc yêu cầu góc máy/ánh sáng/tư thế mới")
        preferredWidth: 540

        property int targetSceneIndex: -1
        property string basePrompt: ""

        function openForScene(sceneIndex, initialPrompt) {
            targetSceneIndex = sceneIndex;
            basePrompt = initialPrompt || "";
            customNotesInput.text = "";
            open();
        }

        ColumnLayout {
            spacing: Theme.space12
            width: parent.width

            Text {
                Layout.fillWidth: true
                text: qsTr("Mô tả prompt hiện tại của cảnh:")
                color: Theme.textMuted
                font.pixelSize: TypeScale.label
                font.weight: Font.DemiBold
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Math.min(100, Math.max(48, basePromptText.implicitHeight + 16))
                radius: Theme.radiusTiny
                color: Theme.surfaceMuted
                border.width: 1
                border.color: Theme.outline

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 8
                    clip: true

                    Text {
                        id: basePromptText
                        width: parent.width
                        text: regenImageDialog.basePrompt || qsTr("(Chưa có prompt)")
                        color: Theme.text
                        font.pixelSize: TypeScale.caption
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Ghi chú bổ sung / Yêu cầu chỉnh sửa:")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.label
            }

            AppTextArea {
                id: customNotesInput
                Layout.fillWidth: true
                Layout.preferredHeight: 76
                placeholderText: qsTr("Ví dụ: nhân vật nhìn sang trái, góc máy từ trên xuống, thêm ánh đèn đường vàng, trời mưa to...")
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("💡 Hệ thống tự động áp dụng harness chuẩn thuần Việt: gương mặt, nhân vật và cảnh quan thuần Việt Nam, giàu chi tiết và tuyệt đối không chứa chữ hay watermark.")
                color: Theme.success
                font.pixelSize: TypeScale.caption
                wrapMode: Text.WordWrap
            }
        }

        footerActions: [
            StudioButton {
                text: qsTr("Hủy")
                compact: true
                onClicked: regenImageDialog.close()
            },
            StudioButton {
                text: customNotesInput.text.trim().length > 0 ? qsTr("Tạo lại theo ghi chú") : qsTr("Tạo biến thể mới")
                iconGlyph: "\uE72C"
                compact: true
                tone: "primary"
                enabled: !root.isBusy && regenImageDialog.targetSceneIndex >= 0
                onClicked: {
                    const idx = regenImageDialog.targetSceneIndex;
                    const notes = customNotesInput.text.trim();
                    regenImageDialog.close();
                    controller.regenerateSceneImageWithNote(idx, notes);
                }
            }
        ]
    }

    AppDialog {
        id: youtubePublishDialog
        title: (controller && controller.aspectRatio === "9:16")
            ? qsTr("Đăng Video lên YouTube Shorts")
            : qsTr("Đăng Video lên YouTube")
        subtitle: controller && controller.youtubeConnected
            ? qsTr("Kênh: %1 • Tải lên trực tiếp qua Google YouTube API").arg(controller.youtubeChannelTitle || qsTr("Đã kết nối"))
            : qsTr("Cần kết nối tài khoản Google YouTube trước khi xuất bản")
        preferredWidth: 540

        function openForCurrentProject() {
            if (!controller) return;
            const isShorts = (controller.aspectRatio === "9:16");
            const rawTitle = (controller.hasProject && controller.articleText)
                ? controller.articleText.slice(0, 50).replace(/\n/g, " ").trim()
                : qsTr("Phim Ngắn Đọc Truyện AI");
            if (isShorts && rawTitle.indexOf("#Shorts") === -1 && rawTitle.indexOf("#shorts") === -1) {
                ytTitleInput.text = rawTitle + " #Shorts";
            } else {
                ytTitleInput.text = rawTitle;
            }

            const storyExcerpt = controller.articleText ? controller.articleText.slice(0, 300).trim() : "";
            if (isShorts) {
                ytDescInput.text = ytTitleInput.text + "\n\n" + storyExcerpt + "\n\n#Shorts #TruyenNgan #PhimNgan #KichBanAI";
                ytTagsInput.text = "Shorts, TruyenNgan, PhimNgan, AI";
            } else {
                ytDescInput.text = ytTitleInput.text + "\n\n" + storyExcerpt + "\n\nVideo được tạo tự động bởi AI.";
                ytTagsInput.text = "TruyenNgan, PhimNgan, AI";
            }
            open();
        }

        ColumnLayout {
            spacing: Theme.space12
            width: parent.width

            // Channel Status Row
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: ytConnRow.implicitHeight + 16
                radius: Theme.radiusTiny
                color: controller && controller.youtubeConnected ? Theme.successSubtle : Theme.surfaceMuted
                border.width: 1
                border.color: controller && controller.youtubeConnected ? Theme.success : Theme.outline

                RowLayout {
                    id: ytConnRow
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    FluentIcon {
                        name: controller && controller.youtubeConnected ? "success" : "link"
                        iconColor: controller && controller.youtubeConnected ? Theme.success : Theme.interactive
                        iconSize: 18
                    }

                    Text {
                        Layout.fillWidth: true
                        text: controller && controller.youtubeConnected
                            ? qsTr("Tài khoản: %1").arg(controller.youtubeChannelTitle || qsTr("Đã xác thực Google"))
                            : qsTr("Chưa kết nối tài khoản Google YouTube")
                        color: Theme.text
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                    }

                    StudioButton {
                        visible: Boolean(!controller || !controller.youtubeConnected)
                        text: qsTr("Kết nối ngay")
                        compact: true
                        tone: "primary"
                        onClicked: if (controller) controller.connectYouTube()
                    }

                    StudioButton {
                        visible: Boolean(controller && controller.youtubeConnected)
                        text: qsTr("Đổi kênh")
                        compact: true
                        onClicked: if (controller) controller.connectYouTube()
                    }
                }
            }

            // Title
            Text {
                text: qsTr("Tiêu đề video:")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.label
            }

            AppTextField {
                id: ytTitleInput
                Layout.fillWidth: true
                placeholderText: qsTr("Nhập tiêu đề video YouTube...")
            }

            // Description
            Text {
                text: qsTr("Mô tả video:")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.label
            }

            AppTextArea {
                id: ytDescInput
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                wrapMode: Text.WordWrap
                placeholderText: qsTr("Mô tả nội dung, hashtag...")
            }

            // Tags
            Text {
                text: qsTr("Thẻ từ khóa (Tags):")
                color: Theme.text
                font.weight: Font.DemiBold
                font.pixelSize: TypeScale.label
            }

            AppTextField {
                id: ytTagsInput
                Layout.fillWidth: true
                placeholderText: qsTr("Shorts, TruyenNgan, PhimNgan, AI...")
            }

            // Privacy Option
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: qsTr("Chế độ hiển thị:")
                    color: Theme.text
                    font.weight: Font.DemiBold
                    font.pixelSize: TypeScale.label
                }
                Item { Layout.fillWidth: true }
                AppComboBox {
                    id: ytPrivacyCombo
                    Layout.preferredWidth: 160
                    model: [
                        { text: qsTr("Công khai (Public)"), value: "public" },
                        { text: qsTr("Không công khai (Unlisted)"), value: "unlisted" },
                        { text: qsTr("Riêng tư (Private)"), value: "private" }
                    ]
                    textRole: "text"
                    valueRole: "value"
                    currentIndex: 0
                    onActivated: if (controller) controller.setYoutubePrivacy(currentValue)
                }
            }

            // Upload Progress Bar
            AppProgressBar {
                Layout.fillWidth: true
                visible: Boolean(controller && controller.isUploadingYoutube)
                value: controller ? controller.youtubeUploadProgress : 0
            }

            // Status message / Link
            Text {
                Layout.fillWidth: true
                text: controller ? controller.youtubeUploadMessage : ""
                color: controller && controller.youtubeVideoUrl ? Theme.success : Theme.textMuted
                font.pixelSize: TypeScale.caption
                wrapMode: Text.Wrap
                visible: text.length > 0
            }
        }

        footerActions: [
            StudioButton {
                text: qsTr("Đóng")
                compact: true
                onClicked: youtubePublishDialog.close()
            },
            StudioButton {
                visible: Boolean(controller && controller.youtubeVideoUrl)
                text: qsTr("Xem trên YouTube")
                iconGlyph: "\uE8A7"
                compact: true
                tone: "secondary"
                onClicked: if (controller) controller.openYouTubeVideo()
            },
            StudioButton {
                text: (controller && controller.aspectRatio === "9:16")
                    ? qsTr("Tải lên YouTube Shorts")
                    : qsTr("Tải lên YouTube")
                iconGlyph: "\uE714"
                compact: true
                tone: "primary"
                enabled: Boolean(controller && !controller.isUploadingYoutube && controller.youtubeConnected && ytTitleInput.text.trim().length > 0)
                onClicked: {
                    if (controller) {
                        controller.uploadToYouTubeWithParams(
                            ytTitleInput.text.trim(),
                            ytDescInput.text.trim(),
                            ytTagsInput.text.trim()
                        );
                    }
                }
            }
        ]
    }
}
