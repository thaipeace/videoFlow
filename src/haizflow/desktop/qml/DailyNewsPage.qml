pragma ComponentBehavior: Bound
// qmllint disable missing-property stale-property-read

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestNavigate(string route)

    readonly property var controller: AppController.dailyNews
    readonly property bool isBusy: controller ? controller.isBusy : false
    readonly property bool isUploading: controller ? controller.uploading : false
    readonly property string activeCategory: controller ? controller.selectedCategory : "world"
    property bool showAdvancedSettings: false
    property string historyFilter: "all"
    property bool bannerDismissed: false

    // Local buffered configuration properties to eliminate UI lag during edits
    property int localMaxTopics: 8
    property string localAspectRatio: "16:9"
    property string localVoiceId: "vi-VN-NamMinhNeural"
    property bool localBgmEnabled: true
    property real localBgmVolume: 0.08
    property bool localAutoUploadYoutube: false
    property string localYoutubePrivacy: "public"
    property bool localAutoAddToPlaylist: true
    property string localPlaylistTitle: "Bản tin thế giới"
    property bool hasUnsavedChanges: false
    property bool saveSuccess: false

    function syncFromController() {
        if (!controller) return;
        localMaxTopics = controller.maxTopics;
        localAspectRatio = controller.aspectRatio;
        localVoiceId = controller.voiceId;
        localBgmEnabled = controller.bgmEnabled;
        localBgmVolume = controller.bgmVolume;
        localAutoUploadYoutube = controller.autoUploadYoutube;
        localYoutubePrivacy = controller.youtubePrivacy;
        localAutoAddToPlaylist = controller.autoAddToPlaylist;
        localPlaylistTitle = controller.currentCategoryPlaylist;
        hasUnsavedChanges = false;
    }

    function commitSettings() {
        if (controller) {
            controller.saveProductionSettings(
                localMaxTopics,
                localAspectRatio,
                localVoiceId,
                localBgmEnabled,
                localBgmVolume,
                localAutoUploadYoutube,
                localYoutubePrivacy,
                localAutoAddToPlaylist,
                localPlaylistTitle
            );
        }
        hasUnsavedChanges = false;
        saveSuccess = true;
        saveSuccessTimer.restart();
    }

    Timer {
        id: saveSuccessTimer
        interval: 3500
        repeat: false
        onTriggered: root.saveSuccess = false
    }

    onActiveCategoryChanged: {
        syncFromController();
    }

    Component.onCompleted: {
        syncFromController();
    }

    onIsBusyChanged: if (isBusy) bannerDismissed = false
    onIsUploadingChanged: if (isUploading) bannerDismissed = false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space12

        // =====================================================================
        // TOP HEADER
        // =====================================================================
        PageHeader {
            Layout.fillWidth: true
            title: root.activeCategory === "war"
                ? qsTr("Bản tin Chiến sự Thế giới - Quản lý & Xuất bản tự động")
                : root.activeCategory === "tech"
                ? qsTr("Bản tin Công nghệ Thế giới - Quản lý & Xuất bản tự động")
                : root.activeCategory === "sports"
                ? qsTr("Bản tin Bóng đá Quốc tế - Quản lý & Xuất bản tự động")
                : root.activeCategory === "viral"
                ? qsTr("Tin Lạ & Hài Hước Thế Giới - Quản lý & Xuất bản tự động")
                : root.activeCategory === "hope"
                ? qsTr("Tin Vui & Sáng Chế Tương Lai - Quản lý & Xuất bản tự động")
                : qsTr("Bản tin Thời sự Thế giới - Quản lý & Xuất bản tự động")

            RowLayout {
                spacing: Theme.space8

                StudioButton {
                    text: qsTr("Làm mới")
                    iconName: "refresh"
                    compact: true
                    enabled: !root.isBusy
                    onClicked: {
                        if (controller) {
                            controller.refreshHistory();
                            controller.refreshScheduleStatus();
                        }
                    }
                }

                StudioButton {
                    text: qsTr("Dừng lại")
                    iconName: "stop"
                    variant: "danger"
                    compact: true
                    visible: root.isBusy
                    onClicked: {
                        if (controller) controller.cancelProduction();
                    }
                }

                StudioButton {
                    text: root.activeCategory === "tin_moi"
                        ? qsTr("Tổng hợp Bản tin Tin Mới")
                        : root.activeCategory === "tin_nong"
                        ? qsTr("Tổng hợp Bản tin Tin Nóng")
                        : root.activeCategory === "hope"
                        ? qsTr("Tổng hợp Short Tin Vui")
                        : root.activeCategory === "viral"
                        ? qsTr("Tổng hợp Short Tin Độc Lạ")
                        : root.activeCategory === "war"
                        ? qsTr("Tổng hợp bản tin Chiến sự")
                        : root.activeCategory === "tech"
                        ? qsTr("Tổng hợp bản tin Công nghệ")
                        : root.activeCategory === "sports"
                        ? qsTr("Tổng hợp bản tin Bóng đá")
                        : qsTr("Tổng hợp bản tin Thời sự")
                    iconName: "play"
                    variant: "primary"
                    compact: false
                    enabled: !root.isBusy
                    onClicked: {
                        if (root.hasUnsavedChanges) {
                            root.commitSettings();
                        }
                        if (controller) controller.startProduction(root.activeCategory);
                    }
                }
            }
        }

        // =====================================================================
        // CATEGORY TABS: TIN MỚI (5H30) / TIN VUI (11H30) / TIN ĐỘC LẠ (12H00) / TIN NÓNG (17H30)
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 50
            radius: Theme.radiusSmall
            color: Theme.surface
            border.width: 1
            border.color: Theme.divider

            RowLayout {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 6

                Repeater {
                    model: [
                        { key: "tin_moi", label: qsTr("Tin Mới (5h30)"), icon: "globe", tag: qsTr("Thế giới + Thể thao"), tagColor: Theme.interactive },
                        { key: "hope", label: qsTr("Short Tin Vui (11h30)"), icon: "favorite", tag: qsTr("Shorts • Hy vọng"), tagColor: "#10B981" },
                        { key: "viral", label: qsTr("Short Tin Độc Lạ (12h00)"), icon: "sparkle", tag: qsTr("Shorts • Lạ & Hài"), tagColor: "#FF5722" },
                        { key: "tin_nong", label: qsTr("Tin Nóng (17h30)"), icon: "shield", tag: qsTr("Chiến sự + Công nghệ"), tagColor: "#E53935" }
                    ]

                    delegate: Control {
                        id: catTabBtn
                        required property var modelData
                        required property int index

                        readonly property bool isSelected: root.activeCategory === modelData.key

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        focusPolicy: Qt.TabFocus

                        background: Rectangle {
                            radius: Theme.radiusSmall - 2
                            color: catTabBtn.isSelected
                                ? Theme.surfaceStrong
                                : (catTabHover.hovered ? Theme.surfaceMuted : "transparent")
                            border.width: catTabBtn.isSelected ? 1 : (catTabBtn.visualFocus ? 2 : 0)
                            border.color: catTabBtn.isSelected ? catTabBtn.modelData.tagColor : Theme.controlFocus

                            // Bottom accent indicator
                            Rectangle {
                                anchors.bottom: parent.bottom
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: catTabBtn.isSelected ? Math.min(parent.width - 24, 120) : 0
                                height: 3
                                radius: 1.5
                                color: catTabBtn.modelData.tagColor
                                visible: catTabBtn.isSelected
                            }
                        }

                        contentItem: RowLayout {
                            spacing: Theme.space8
                            anchors.centerIn: parent

                            FluentIcon {
                                name: catTabBtn.modelData.icon
                                iconSize: 18
                                iconColor: catTabBtn.isSelected ? catTabBtn.modelData.tagColor : Theme.textMuted
                            }

                            Text {
                                text: catTabBtn.modelData.label
                                color: catTabBtn.isSelected ? Theme.text : Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.control
                                font.weight: catTabBtn.isSelected ? Font.Bold : Font.Medium
                            }

                            Rectangle {
                                implicitHeight: 18
                                implicitWidth: tagTxt.implicitWidth + 12
                                radius: 9
                                color: catTabBtn.isSelected
                                    ? Qt.alpha(catTabBtn.modelData.tagColor, 0.16)
                                    : Theme.input
                                visible: !UiMetrics.compactLayout

                                Text {
                                    id: tagTxt
                                    anchors.centerIn: parent
                                    text: catTabBtn.modelData.tag
                                    color: catTabBtn.isSelected ? catTabBtn.modelData.tagColor : Theme.textDisabled
                                    font.pixelSize: TypeScale.metadata - 1
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        HoverHandler { id: catTabHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: {
                                if (root.hasUnsavedChanges) {
                                    root.commitSettings();
                                }
                                if (controller) controller.setSelectedCategory(catTabBtn.modelData.key);
                            }
                        }
                    }
                }
            }
        }

        // =====================================================================
        // EXECUTION & PROGRESS BANNER
        // =====================================================================
        Rectangle {
            id: bannerBox
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(125, bannerLayout.implicitHeight + Theme.space12 * 2)
            Layout.maximumHeight: 130
            clip: true
            visible: !root.bannerDismissed && Boolean(controller && (root.isBusy || controller.status === "completed" || controller.status === "error" || root.isUploading || (controller.uploadMessage && controller.uploadMessage.length > 0)))
            radius: Theme.radiusSmall
            color: controller && (controller.status === "error" || (controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1)) ? Theme.dangerSubtle
                : controller && controller.status === "completed" ? Theme.successSubtle
                : Theme.interactiveSubtle
            border.width: 1
            border.color: controller && (controller.status === "error" || (controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1)) ? Theme.danger
                : controller && controller.status === "completed" ? Theme.success
                : Theme.interactive

            RowLayout {
                id: bannerLayout
                anchors.fill: parent
                anchors.margins: Theme.space12
                spacing: Theme.space12

                FluentIcon {
                    name: controller && (controller.status === "error" || (controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1)) ? "error"
                        : controller && controller.status === "completed" ? "success"
                        : "info"
                    iconSize: 22
                    iconColor: controller && (controller.status === "error" || (controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1)) ? Theme.danger
                        : controller && controller.status === "completed" ? Theme.success
                        : Theme.interactive
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    spacing: Theme.space4

                    Text {
                        Layout.fillWidth: true
                        text: controller ? (controller.status === "error" || (controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1) ? qsTr("Thông báo / Trạng thái") : qsTr("Trạng thái quy trình")) : ""
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.label
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: controller ? controller.progressMessage : ""
                        color: controller && controller.status === "error" ? "#FFDAD6" : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        wrapMode: Text.Wrap
                        maximumLineCount: 1
                        elide: Text.ElideRight
                    }

                    // Direct Upload notification if active
                    RowLayout {
                        Layout.fillWidth: true
                        visible: Boolean(controller && controller.uploadMessage && controller.uploadMessage.length > 0)
                        spacing: Theme.space8

                        PlatformLogo {
                            platform: "youtube"
                        }

                        Text {
                            Layout.fillWidth: true
                            text: controller ? controller.uploadMessage : ""
                            color: controller && controller.uploadMessage.indexOf("thất bại") !== -1 ? "#FFB4AB" : Theme.interactive
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.control
                            font.weight: Font.Medium
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }
                }

                RowLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: Theme.space8

                    // Link to activate YouTube API on Google Cloud if disabled
                    StudioButton {
                        visible: Boolean(controller && controller.uploadMessage && (
                            controller.uploadMessage.indexOf("SERVICE_DISABLED") !== -1 ||
                            controller.uploadMessage.indexOf("YouTube Data API v3") !== -1 ||
                            controller.uploadMessage.indexOf("console.developers.google.com") !== -1 ||
                            controller.uploadMessage.indexOf("704435039379") !== -1
                        ))
                        text: qsTr("Kích hoạt Google API")
                        iconName: "link"
                        variant: "primary"
                        compact: true
                        onClicked: {
                            if (controller) controller.openExternalUrl("https://console.developers.google.com/apis/api/youtube.googleapis.com/overview?project=704435039379");
                            else Qt.openUrlExternally("https://console.developers.google.com/apis/api/youtube.googleapis.com/overview?project=704435039379");
                        }
                    }

                    // Retry upload button if upload failed and we have a video
                    StudioButton {
                        visible: Boolean(controller && controller.uploadMessage && controller.uploadMessage.indexOf("thất bại") !== -1 && controller.lastVideoPath)
                        text: qsTr("Thử lại tải YouTube")
                        iconName: "refresh"
                        variant: "primary"
                        compact: true
                        enabled: !root.isBusy && !root.isUploading
                        onClicked: {
                            if (controller && controller.lastVideoPath) {
                                controller.publishVideo(controller.lastVideoPath, "youtube");
                            }
                        }
                    }

                    StudioButton {
                        visible: Boolean(controller && controller.status === "completed" && controller.lastVideoPath)
                        text: qsTr("Xem video")
                        variant: "secondary"
                        iconName: "play"
                        compact: true
                        onClicked: {
                            if (controller) controller.openVideoFile(controller.lastVideoPath);
                        }
                    }

                    StudioButton {
                        visible: Boolean(controller && controller.status === "completed" && controller.lastVideoPath)
                        text: qsTr("Mở thư mục")
                        iconName: "folder"
                        compact: true
                        onClicked: {
                            if (controller) controller.openOutputDir(controller.lastVideoPath);
                        }
                    }

                    // Dismiss / Close button
                    IconButton {
                        glyph: IconCatalog.glyph("close")
                        tone: "ghost"
                        controlSize: 28
                        toolTipText: qsTr("Đóng thông báo này")
                        showToolTip: true
                        onClicked: {
                            root.bannerDismissed = true;
                            if (controller) controller.dismissBanner();
                        }
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

        // =====================================================================
        // MAIN WORKSPACE CONTENT: 2-COLUMN DASHBOARD
        // =====================================================================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space16

            // -----------------------------------------------------------------
            // LEFT COLUMN: Cấu hình sản xuất & Tự động xuất bản mạng xã hội
            // -----------------------------------------------------------------
            ScrollView {
                Layout.preferredWidth: 470
                Layout.minimumWidth: 380
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    width: parent.width - 12
                    spacing: Theme.space12

                    // CARD 1: CẤU HÌNH SẢN XUẤT BẢN TIN (FOCUS VÀO CẤU HÌNH THÀNH CÔNG GẦN NHẤT)
                    AppSurface {
                        Layout.fillWidth: true
                        tone: "default"
                        padding: Theme.space16
                        spacing: Theme.space12

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            FluentIcon {
                                name: root.activeCategory === "war" ? "shield"
                                    : root.activeCategory === "tech" ? "tech"
                                    : root.activeCategory === "sports" ? "sports"
                                    : root.activeCategory === "viral" ? "sparkle"
                                    : root.activeCategory === "hope" ? "favorite"
                                    : "globe"
                                iconSize: 18
                                iconColor: root.activeCategory === "war" ? "#E53935"
                                    : root.activeCategory === "tech" ? "#9B51E0"
                                    : root.activeCategory === "sports" ? "#27AE60"
                                    : root.activeCategory === "viral" ? "#FF5722"
                                    : root.activeCategory === "hope" ? "#10B981"
                                    : Theme.interactive
                            }

                            Text {
                                text: root.activeCategory === "war"
                                    ? qsTr("1. Cấu hình Bản tin Chiến sự")
                                    : root.activeCategory === "tech"
                                    ? qsTr("1. Cấu hình Bản tin Công nghệ")
                                    : root.activeCategory === "sports"
                                    ? qsTr("1. Cấu hình Bản tin Bóng đá")
                                    : root.activeCategory === "viral"
                                    ? qsTr("1. Cấu hình Tin Lạ & Hài Hước (Shorts)")
                                    : root.activeCategory === "hope"
                                    ? qsTr("1. Cấu hình Tin Vui & Sáng Chế (Shorts)")
                                    : qsTr("1. Cấu hình Bản tin Thời sự")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.section
                                font.weight: Font.Bold
                            }

                            Item { Layout.fillWidth: true }

                            StatusBadge {
                                status: "success"
                                label: qsTr("Chuẩn YouTube (Đã tối ưu)")
                            }
                        }

                        // Preset summary box - Focus on the winning production configuration
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: presetSummaryCol.implicitHeight + Theme.space12 * 2
                            radius: Theme.radiusSmall
                            color: Theme.surfaceMuted
                            border.width: 1
                            border.color: Theme.outline

                            ColumnLayout {
                                id: presetSummaryCol
                                anchors.fill: parent
                                anchors.margins: Theme.space12
                                spacing: Theme.space8

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: qsTr("• Định dạng video:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        Layout.preferredWidth: 140
                                    }
                                    Text {
                                        text: root.localAspectRatio === "9:16" ? qsTr("9:16 Dọc Shorts/Reels (1080x1920)") : qsTr("16:9 Ngang YouTube (1080p Full HD)")
                                        color: Theme.text
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: qsTr("• Quy mô bản tin:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        Layout.preferredWidth: 140
                                    }
                                    Text {
                                        text: root.localMaxTopics + (
                                            root.activeCategory === "war"
                                                ? qsTr(" điểm nóng chiến sự & địa chính trị (~6 - 8 phút)")
                                                : root.activeCategory === "tech"
                                                ? qsTr(" sự kiện công nghệ & AI (~6 - 8 phút)")
                                                : root.activeCategory === "sports"
                                                ? qsTr(" sự kiện bóng đá đỉnh cao (~6 - 8 phút)")
                                                : root.activeCategory === "viral"
                                                ? qsTr(" tin lạ & hài hước (~60 giây)")
                                                : root.activeCategory === "hope"
                                                ? qsTr(" phát minh & tin vui hy vọng (~50 giây)")
                                                : qsTr(" sự kiện thế giới toàn diện (~6 - 8 phút)")
                                        )
                                        color: Theme.text
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: qsTr("• Giọng phát thanh:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        Layout.preferredWidth: 140
                                    }
                                    Text {
                                        text: root.localVoiceId === "multi_trio"
                                            ? qsTr("🎲 Luân phiên 3 giọng (Nam Minh, Hoài My, Đà Lạt)")
                                            : root.localVoiceId === "vi-VN-HoaiMyNeural"
                                            ? qsTr("Hoài My (Nữ - Sài Gòn, Truyền cảm nhẹ nhàng)")
                                            : root.localVoiceId === "vi-VN-DaLatNeural"
                                            ? qsTr("Đà Lạt (Nữ - Miền Nam, Tự nhiên rõ chữ)")
                                            : root.localVoiceId === "vi-VN-QuangDungNeural"
                                            ? qsTr("Quang Dũng (Nam - Miền Trung, Vững chắc)")
                                            : qsTr("Nam Minh (Nam - Hà Nội, Trầm ấm chuẩn VTV)")
                                        color: Theme.text
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: qsTr("• Âm thanh & Âm hiệu:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        Layout.preferredWidth: 140
                                    }
                                    Text {
                                        text: root.localBgmEnabled
                                            ? qsTr("BGM hào hứng (%1%) + TV Stinger (dạo 450ms)").arg(Math.round(root.localBgmVolume * 100))
                                            : qsTr("Tắt BGM (Chỉ phát giọng đọc AI)")
                                        color: Theme.text
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: qsTr("• Nguồn quốc tế:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        Layout.preferredWidth: 140
                                    }
                                    Text {
                                        text: root.activeCategory === "war"
                                            ? qsTr("Reuters, AP, ISW (Viện NC Chiến tranh), Al Jazeera, BBC")
                                            : root.activeCategory === "tech"
                                            ? qsTr("The Verge, TechCrunch, Wired, Ars Technica, BBC Tech")
                                            : root.activeCategory === "sports"
                                            ? qsTr("BBC Football, Sky Sports Football, The Guardian Football, ESPN FC")
                                            : root.activeCategory === "viral"
                                            ? qsTr("UPI Odd News, Reddit r/nottheonion, r/funny, Oddity Central, Viral Fails & Clips")
                                            : root.activeCategory === "hope"
                                            ? qsTr("Good News Network, Optimist Daily, ScienceDaily, New Atlas")
                                            : qsTr("Reuters, BBC, AP, The Guardian, Al Jazeera")
                                        color: Theme.text
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }

                        // Toggle button for advanced adjustments
                        RowLayout {
                            Layout.fillWidth: true

                            Item { Layout.fillWidth: true }

                            StudioButton {
                                text: root.showAdvancedSettings ? qsTr("Thu gọn tùy chỉnh ▲") : qsTr("Tùy chỉnh thêm (Nâng cao) ▼")
                                variant: "ghost"
                                compact: true
                                onClicked: root.showAdvancedSettings = !root.showAdvancedSettings
                            }
                        }

                        // Advanced Customization Section (Collapsible)
                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: root.showAdvancedSettings
                            spacing: Theme.space8

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: Theme.divider
                            }

                            // Số lượng tin tức
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space4

                                Text {
                                    text: qsTr("Số lượng tin tức:")
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.label
                                }

                                SegmentedControl {
                                    Layout.fillWidth: true
                                    enabled: !root.isBusy
                                    currentValue: String(root.localMaxTopics)
                                    options: root.localAspectRatio === "9:16" ? [
                                        { label: qsTr("Top 3 (Shorts chuẩn)"), value: "3" },
                                        { label: qsTr("5 tin vắn"), value: "5" },
                                        { label: qsTr("8 tin chi tiết"), value: "8" }
                                    ] : [
                                        { label: qsTr("5 tin vắn"), value: "5" },
                                        { label: qsTr("8 tin (khuyên dùng)"), value: "8" },
                                        { label: qsTr("10 tin chi tiết"), value: "10" }
                                    ]
                                    onActivated: function(val) {
                                        root.localMaxTopics = parseInt(val);
                                        root.hasUnsavedChanges = true;
                                    }
                                }
                            }

                            // Tỷ lệ khung hình
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space4

                                Text {
                                    text: qsTr("Tỷ lệ khung hình:")
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.label
                                }

                                SegmentedControl {
                                    Layout.fillWidth: true
                                    enabled: !root.isBusy
                                    currentValue: root.localAspectRatio
                                    options: [
                                        { label: qsTr("16:9 Ngang YouTube (Chuẩn)"), value: "16:9" },
                                        { label: qsTr("9:16 Dọc Shorts/Reels"), value: "9:16" }
                                    ]
                                    onActivated: function(val) {
                                        root.localAspectRatio = val;
                                        root.hasUnsavedChanges = true;
                                    }
                                }
                            }

                            // Giọng đọc AI
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space4

                                Text {
                                    text: qsTr("Giọng đọc AI:")
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.label
                                }

                                AppComboBox {
                                    id: voiceCombo
                                    Layout.fillWidth: true
                                    enabled: !root.isBusy
                                    model: [
                                        { name: "Nam Minh (Nam - Hà Nội, Trầm ấm chuẩn VTV)", id: "vi-VN-NamMinhNeural" },
                                        { name: "Hoài My (Nữ - Sài Gòn, Truyền cảm nhẹ nhàng)", id: "vi-VN-HoaiMyNeural" },
                                        { name: "Đà Lạt (Nữ - Miền Nam, Tự nhiên rõ chữ)", id: "vi-VN-DaLatNeural" },
                                        { name: "Quang Dũng (Nam - Miền Trung, Vững chắc)", id: "vi-VN-QuangDungNeural" },
                                        { name: "🎲 Luân phiên 3 giọng (Nam Minh, Hoài My, Đà Lạt)", id: "multi_trio" }
                                    ]
                                    textRole: "name"
                                    valueRole: "id"
                                    currentIndex: {
                                        for (let i = 0; i < model.length; i++) {
                                            if (model[i].id === root.localVoiceId) return i;
                                        }
                                        return 0;
                                    }
                                    onActivated: function(index) {
                                        if (model[index]) {
                                            root.localVoiceId = model[index].id;
                                            root.hasUnsavedChanges = true;
                                        }
                                    }
                                }
                            }

                            // Nhạc nền (BGM) & Âm lượng
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Theme.space4

                                AppSwitch {
                                    text: qsTr("Nhạc nền thời sự hào hứng (BGM)")
                                    enabled: !root.isBusy
                                    checked: root.localBgmEnabled
                                    onToggled: {
                                        root.localBgmEnabled = checked;
                                        root.hasUnsavedChanges = true;
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    visible: root.localBgmEnabled
                                    spacing: Theme.space8

                                    Text {
                                        text: qsTr("Âm lượng:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.label
                                    }

                                    AppSlider {
                                        Layout.fillWidth: true
                                        enabled: !root.isBusy
                                        from: 0.02
                                        to: 0.20
                                        stepSize: 0.01
                                        value: root.localBgmVolume
                                        onMoved: {
                                            root.localBgmVolume = value;
                                            root.hasUnsavedChanges = true;
                                        }
                                    }

                                    Text {
                                        Layout.preferredWidth: 36
                                        text: Math.round(root.localBgmVolume * 100) + "%"
                                        color: Theme.text
                                        font.pixelSize: TypeScale.label
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }
                    }
                    // CARD 2: PHƯƠNG ÁN 1 - GOOGLE YOUTUBE DATA API V3 (UPLOAD TRỰC TIẾP KHÔNG CẦN ZERNIO)
                    AppSurface {
                        Layout.fillWidth: true
                        tone: "default"
                        padding: Theme.space16
                        spacing: Theme.space12

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            PlatformLogo {
                                platform: "youtube"
                            }

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("2. Xuất bản YouTube (Google API Trực tiếp)")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.section
                                font.weight: Font.Bold
                            }

                            StatusBadge {
                                status: controller && controller.youtubeConnected ? "success" : "ready"
                                label: controller && controller.youtubeConnected ? qsTr("Đã kết nối") : qsTr("Chưa kết nối")
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Đăng thẳng video 1080p từ máy tính của bạn lên YouTube qua Google API chính thức. Miễn phí 100%, không cần qua bên thứ ba.")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.control
                            wrapMode: Text.Wrap
                        }

                        // --- YouTube Account Connection Box ---
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: ytAuthBoxCol.implicitHeight + Theme.space12 * 2
                            radius: Theme.radiusSmall
                            color: controller && controller.youtubeConnected ? Theme.successSubtle : Theme.surfaceMuted
                            border.width: 1
                            border.color: controller && controller.youtubeConnected ? Theme.success : Theme.outline

                            ColumnLayout {
                                id: ytAuthBoxCol
                                anchors.fill: parent
                                anchors.margins: Theme.space12
                                spacing: Theme.space8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space8

                                    FluentIcon {
                                        name: controller && controller.youtubeConnected ? "success" : "link"
                                        iconSize: 18
                                        iconColor: controller && controller.youtubeConnected ? Theme.success : Theme.interactive
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: controller && controller.youtubeConnected
                                            ? qsTr("Kênh: ") + controller.youtubeChannelTitle
                                            : qsTr("Chưa kết nối tài khoản Google YouTube")
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: TypeScale.control
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    // Action button when connected
                                    StudioButton {
                                        visible: Boolean(controller && controller.youtubeConnected)
                                        text: qsTr("Ngắt kết nối")
                                        variant: "danger"
                                        compact: true
                                        onClicked: {
                                            if (controller) controller.disconnectYouTube();
                                        }
                                    }
                                }

                                // Actions when NOT connected
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: Boolean(!controller || !controller.youtubeConnected)
                                    spacing: Theme.space8

                                    Text {
                                        Layout.fillWidth: true
                                        text: qsTr("Nhập tệp client_secret.json tải từ Google Cloud Console để cấp quyền đăng tải:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.metadata
                                        wrapMode: Text.Wrap
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        StudioButton {
                                            text: qsTr("Nhập client_secret.json")
                                            iconName: "folder"
                                            variant: "primary"
                                            compact: true
                                            onClicked: {
                                                if (controller) controller.pickAndImportClientSecret();
                                            }
                                        }

                                        StudioButton {
                                            text: qsTr("Kết nối kênh Google")
                                            iconName: "share"
                                            variant: "secondary"
                                            compact: true
                                            enabled: Boolean(controller && controller.hasYouTubeClientSecret)
                                            onClicked: {
                                                if (controller) controller.connectYouTube();
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // --- Auto Upload Switch & Privacy & Playlist ---
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            AppSwitch {
                                Layout.fillWidth: true
                                text: qsTr("Tự động upload lên YouTube khi tổng hợp xong")
                                enabled: !root.isBusy
                                checked: root.localAutoUploadYoutube
                                onToggled: {
                                    root.localAutoUploadYoutube = checked;
                                    root.hasUnsavedChanges = true;
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                visible: root.localAutoUploadYoutube
                                spacing: Theme.space8

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space4

                                    Text {
                                        text: qsTr("Quyền riêng tư video YouTube:")
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.label
                                    }

                                    SegmentedControl {
                                        Layout.fillWidth: true
                                        enabled: !root.isBusy
                                        currentValue: root.localYoutubePrivacy
                                        options: [
                                            { label: qsTr("Công khai (Public)"), value: "public" },
                                            { label: qsTr("Không công khai (Unlisted)"), value: "unlisted" },
                                            { label: qsTr("Riêng tư (Private)"), value: "private" }
                                        ]
                                        onActivated: function(val) {
                                            root.localYoutubePrivacy = val;
                                            root.hasUnsavedChanges = true;
                                        }
                                    }
                                }

                                // Playlist option
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.space4

                                    AppCheckBox {
                                        id: playlistCheckBox
                                        text: qsTr("Tự động thêm vào Danh sách phát (Playlist)")
                                        checked: root.localAutoAddToPlaylist
                                        enabled: !root.isBusy
                                        onToggled: {
                                            root.localAutoAddToPlaylist = checked;
                                            root.hasUnsavedChanges = true;
                                        }
                                    }

                                    RowLayout {
                                        visible: playlistCheckBox.checked
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        Text {
                                            text: qsTr("Tên Playlist:")
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.control
                                        }

                                        AppTextField {
                                            Layout.fillWidth: true
                                            text: root.localPlaylistTitle
                                            placeholderText: qsTr("Bản tin thế giới")
                                            enabled: !root.isBusy
                                            onTextChanged: {
                                                if (root.localPlaylistTitle !== text) {
                                                    root.localPlaylistTitle = text;
                                                    root.hasUnsavedChanges = true;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // =========================================================
                    // SAVE CONFIGURATION ACTION BAR (ZERO-LAG SAVE BUTTON)
                    // =========================================================
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: saveActionRow.implicitHeight + Theme.space12 * 2
                        radius: Theme.radiusSmall
                        color: root.hasUnsavedChanges ? Theme.interactiveSubtle : Theme.surface
                        border.width: 1
                        border.color: root.hasUnsavedChanges ? Theme.interactive : Theme.divider

                        RowLayout {
                            id: saveActionRow
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: Theme.space8

                            FluentIcon {
                                name: root.hasUnsavedChanges ? "edit" : "save"
                                iconSize: 18
                                iconColor: root.hasUnsavedChanges ? Theme.interactive : (root.saveSuccess ? Theme.success : Theme.textMuted)
                            }

                            ColumnLayout {
                                spacing: 2
                                Layout.fillWidth: true

                                Text {
                                    text: root.hasUnsavedChanges
                                        ? qsTr("Đang có thay đổi cấu hình chưa lưu")
                                        : (root.saveSuccess ? qsTr("Đã lưu cấu hình thành công!") : qsTr("Cấu hình sản xuất & xuất bản"))
                                    color: root.hasUnsavedChanges ? Theme.interactive : (root.saveSuccess ? Theme.success : Theme.text)
                                    font.family: Theme.fontFamily
                                    font.pixelSize: TypeScale.control
                                    font.weight: Font.DemiBold
                                }

                                Text {
                                    text: root.hasUnsavedChanges
                                        ? qsTr("Nhấn 'Lưu cấu hình' để áp dụng các thiết lập vừa chỉnh.")
                                        : qsTr("Áp dụng cho chuyên mục: %1").arg(
                                            root.activeCategory === "war" ? qsTr("Chiến sự")
                                            : root.activeCategory === "tech" ? qsTr("Công nghệ")
                                            : root.activeCategory === "sports" ? qsTr("Bóng đá")
                                            : root.activeCategory === "viral" ? qsTr("Tin Lạ & Hài")
                                            : root.activeCategory === "hope" ? qsTr("Tin Vui")
                                            : qsTr("Thời sự")
                                        )
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.metadata
                                    elide: Text.ElideRight
                                }
                            }

                            StudioButton {
                                visible: root.hasUnsavedChanges
                                text: qsTr("Hủy")
                                variant: "ghost"
                                compact: true
                                enabled: !root.isBusy
                                onClicked: {
                                    root.syncFromController();
                                }
                            }

                            StudioButton {
                                text: root.hasUnsavedChanges ? qsTr("Lưu cấu hình") : (root.saveSuccess ? qsTr("Đã lưu ✓") : qsTr("Lưu cấu hình"))
                                iconName: root.saveSuccess ? "success" : "check"
                                variant: root.hasUnsavedChanges ? "primary" : "secondary"
                                compact: false
                                enabled: !root.isBusy && (root.hasUnsavedChanges || !root.saveSuccess)
                                onClicked: {
                                    root.commitSettings();
                                }
                            }
                        }
                    }
                    // CARD 3: LẬP LỊCH TỰ ĐỘNG (WINDOWS TASK SCHEDULER)
                    AppSurface {
                        Layout.fillWidth: true
                        tone: "default"
                        padding: Theme.space16
                        spacing: Theme.space12

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            FluentIcon {
                                name: "clock"
                                iconSize: 18
                                iconColor: Theme.interactive
                            }

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("3. Lập lịch phát sóng tự động")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.section
                                font.weight: Font.Bold
                            }

                            StatusBadge {
                                status: "ready"
                                label: qsTr("Windows Task Scheduler")
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Cấu hình giờ sản xuất tự động hàng ngày cho từng chuyên mục tin. Hệ thống tự động khởi chạy và đăng bài ngay cả khi phần mềm đang đóng.")
                            color: Theme.textMuted
                            font.pixelSize: TypeScale.control
                            wrapMode: Text.Wrap
                        }

                        // Resource Advisory Tip Banner
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: schedTipLayout.implicitHeight + Theme.space12 * 2
                            radius: Theme.radiusSmall
                            color: Theme.surfaceMuted
                            border.width: 1
                            border.color: Theme.outline

                            RowLayout {
                                id: schedTipLayout
                                anchors.fill: parent
                                anchors.margins: Theme.space12
                                spacing: Theme.space12

                                FluentIcon {
                                    name: "info"
                                    iconSize: 20
                                    iconColor: Theme.interactive
                                    Layout.alignment: Qt.AlignTop
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("Chiến lược xuất bản tự động:\n• Buổi sáng (05:30): Bản tin Tin Mới (Thế giới + Thể thao, 16:9 ngang)\n• Buổi trưa: Short Tin Vui (11:30) & Short Tin Độc Lạ (12:00, 9:16 Shorts)\n• Buổi tối (17:30): Bản tin Tin Nóng (Chiến sự + Công nghệ, 16:9 ngang)")
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.metadata
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        // Category Schedules List
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            Repeater {
                                model: controller ? controller.categorySchedules : []

                                delegate: Rectangle {
                                    id: schedItemRect
                                    required property var modelData
                                    required property int index

                                    Layout.fillWidth: true
                                    radius: Theme.radiusSmall
                                    color: Theme.surfaceMuted
                                    border.width: 1
                                    border.color: modelData.active ? (modelData.tagColor || Theme.interactive) : Theme.divider
                                    implicitHeight: schedContentLayout.implicitHeight + Theme.space16

                                    ColumnLayout {
                                        id: schedContentLayout
                                        anchors.fill: parent
                                        anchors.margins: Theme.space8
                                        spacing: Theme.space8

                                        // Item Header
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: Theme.space8

                                            FluentIcon {
                                                name: modelData.icon || "news"
                                                iconSize: 16
                                                iconColor: modelData.tagColor || Theme.interactive
                                            }

                                            Text {
                                                text: modelData.label || modelData.name || ""
                                                color: Theme.text
                                                font.pixelSize: TypeScale.control
                                                font.weight: Font.DemiBold
                                            }

                                            StatusBadge {
                                                status: modelData.active ? "success" : "ready"
                                                label: modelData.active ? qsTr("Đang bật (%1)").arg(modelData.time) : qsTr("Chưa bật")
                                            }

                                            Item { Layout.fillWidth: true }
                                        }

                                        // Schedule Controls Row
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: Theme.space8

                                            Text {
                                                text: qsTr("Giờ chạy:")
                                                color: Theme.textMuted
                                                font.pixelSize: TypeScale.control
                                            }

                                            AppTextField {
                                                id: schedTimeField
                                                Layout.preferredWidth: 80
                                                text: modelData.time
                                                placeholderText: "05:00"
                                                enabled: !root.isBusy
                                                onEditingFinished: {
                                                    if (controller) controller.setCategoryScheduleTime(modelData.category, text);
                                                }
                                            }

                                            AppCheckBox {
                                                id: schedWakeBox
                                                text: qsTr("Wake PC")
                                                checked: modelData.wake_up
                                                enabled: !root.isBusy
                                                onToggled: {
                                                    if (controller) controller.setCategoryScheduleWakeUp(modelData.category, checked);
                                                }
                                            }

                                            Item { Layout.fillWidth: true }

                                            StudioButton {
                                                visible: !modelData.active
                                                text: qsTr("Kích hoạt")
                                                variant: "primary"
                                                iconName: "play"
                                                compact: true
                                                enabled: !root.isBusy
                                                onClicked: {
                                                    if (controller) {
                                                        controller.configureCategorySchedule(modelData.category, schedTimeField.text, schedWakeBox.checked);
                                                    }
                                                }
                                            }

                                            StudioButton {
                                                visible: modelData.active
                                                text: qsTr("Cập nhật")
                                                variant: "secondary"
                                                iconName: "refresh"
                                                compact: true
                                                enabled: !root.isBusy
                                                onClicked: {
                                                    if (controller) {
                                                        controller.configureCategorySchedule(modelData.category, schedTimeField.text, schedWakeBox.checked);
                                                    }
                                                }
                                            }

                                            StudioButton {
                                                visible: modelData.active
                                                text: qsTr("Hủy lịch")
                                                variant: "danger"
                                                iconName: "close"
                                                compact: true
                                                enabled: !root.isBusy
                                                onClicked: {
                                                    if (controller) {
                                                        controller.removeCategorySchedule(modelData.category);
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Background Task Info Box
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: bgTaskInfoLayout.implicitHeight + Theme.space12 * 2
                            radius: Theme.radiusSmall
                            color: Theme.surfaceMuted
                            border.width: 1
                            border.color: Theme.outline

                            RowLayout {
                                id: bgTaskInfoLayout
                                anchors.fill: parent
                                anchors.margins: Theme.space12
                                spacing: Theme.space12

                                FluentIcon {
                                    name: "desktop"
                                    iconSize: 20
                                    iconColor: Theme.interactive
                                    Layout.alignment: Qt.AlignTop
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("Lập lịch độc lập bằng Windows Task Scheduler chạy ngầm định kỳ; bạn có thể đóng phần mềm HaizFlow và tắt màn hình, máy tính sẽ tự động kích hoạt tiến trình sản xuất và đăng tải video đúng giờ.")
                                    color: Theme.textMuted
                                    font.pixelSize: TypeScale.metadata
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }
            // RIGHT COLUMN: LỊCH SỬ & KHO LƯU TRỮ BẢN TIN ĐÃ XUẤT BẢN
            // -----------------------------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Theme.radiusSmall
                color: Theme.surface
                border.width: 1
                border.color: Theme.divider

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space16
                    spacing: Theme.space12

                    // Archive Header
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        FluentIcon {
                            name: "folder"
                            iconSize: 20
                            iconColor: Theme.interactive
                        }

                        Text {
                            text: qsTr("Kho lưu trữ bản tin đã xuất bản")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.section
                            font.weight: Font.Bold
                        }

                        StatusBadge {
                            status: "ready"
                            label: (controller && controller.historyList ? controller.historyList.length : 0) + qsTr(" bản tin")
                        }

                        Item { Layout.fillWidth: true }

                        StudioButton {
                            text: qsTr("Kho kịch bản thô (Proof of Work)")
                            iconName: "text"
                            variant: "secondary"
                            compact: true
                            onClicked: {
                                if (controller) controller.openScriptsFolder();
                            }
                        }

                        StudioButton {
                            text: qsTr("Làm mới")
                            iconName: "refresh"
                            compact: true
                            onClicked: {
                                if (controller) controller.refreshHistory();
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    // Archive Category & YouTube Status Filter
                    SegmentedControl {
                        Layout.fillWidth: true
                        currentValue: root.historyFilter
                        options: [
                            { label: qsTr("Tất cả"), value: "all" },
                            { label: qsTr("Thời sự"), value: "world" },
                            { label: qsTr("Chiến sự"), value: "war" },
                            { label: qsTr("Công nghệ"), value: "tech" },
                            { label: qsTr("Bóng đá"), value: "sports" },
                            { label: qsTr("Tin Lạ & Hài"), value: "viral" },
                            { label: qsTr("Tin Vui"), value: "hope" },
                            { label: qsTr("Đã đăng"), value: "youtube_published" },
                            { label: qsTr("Chưa đăng"), value: "not_published" }
                        ]
                        onActivated: function(val) {
                            root.historyFilter = val;
                        }
                    }

                    // Empty state when no history exists
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: !controller || !controller.historyList || controller.historyList.length === 0

                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: Theme.space12

                            FluentIcon {
                                Layout.alignment: Qt.AlignHCenter
                                name: "video"
                                iconSize: 48
                                iconColor: Theme.textDisabled
                            }

                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: qsTr("Chưa có bản tin nào được xuất bản")
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.section
                                font.weight: Font.DemiBold
                            }

                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: qsTr("Nhấn 'Tổng hợp bản tin' ở góc trên để bắt đầu sản xuất bản tin đầu tiên.")
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.control
                            }
                        }
                    }

                    // Broadcast History List
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        visible: Boolean(controller && controller.historyList && controller.historyList.length > 0)

                        ListView {
                            id: historyListView
                            width: parent.width - 8
                            spacing: Theme.space12
                            model: {
                                if (!controller || !controller.historyList) return [];
                                if (root.historyFilter === "all") return controller.historyList;
                                if (root.historyFilter === "youtube_published") {
                                    return controller.historyList.filter(function(it) { return Boolean(it.youtube_published); });
                                }
                                if (root.historyFilter === "not_published") {
                                    return controller.historyList.filter(function(it) { return !Boolean(it.youtube_published); });
                                }
                                return controller.historyList.filter(function(it) {
                                    return (it.category || "world") === root.historyFilter;
                                });
                            }

                            delegate: Rectangle {
                                id: historyCard
                                required property var modelData
                                required property int index

                                width: historyListView.width
                                height: cardContent.implicitHeight + Theme.space16 * 2
                                radius: Theme.radiusSmall
                                color: Theme.surfaceMuted
                                border.width: 1
                                border.color: Theme.outline

                                ColumnLayout {
                                    id: cardContent
                                    anchors.fill: parent
                                    anchors.margins: Theme.space16
                                    spacing: Theme.space12

                                    // Top Row: Title, Category, YouTube Status, Badges
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        Text {
                                            Layout.fillWidth: true
                                            text: historyCard.modelData.title || qsTr("Bản Tin Thời Sự Thế Giới")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: TypeScale.section
                                            font.weight: Font.Bold
                                            elide: Text.ElideRight
                                        }

                                        // Category Badge
                                        Rectangle {
                                            implicitHeight: 20
                                            implicitWidth: catBadgeTxt.implicitWidth + 12
                                            radius: 10
                                            color: (historyCard.modelData.category === "war") ? "#381B1B"
                                                : (historyCard.modelData.category === "tech") ? "#2D1D45"
                                                : (historyCard.modelData.category === "sports") ? "#163828"
                                                : (historyCard.modelData.category === "viral") ? "#382014"
                                                : (historyCard.modelData.category === "hope") ? "#11382A"
                                                : "#1B2A4A"
                                            border.width: 1
                                            border.color: (historyCard.modelData.category === "war") ? "#E53935"
                                                : (historyCard.modelData.category === "tech") ? "#9B51E0"
                                                : (historyCard.modelData.category === "sports") ? "#27AE60"
                                                : (historyCard.modelData.category === "viral") ? "#FF5722"
                                                : (historyCard.modelData.category === "hope") ? "#10B981"
                                                : Theme.interactive

                                            Text {
                                                id: catBadgeTxt
                                                anchors.centerIn: parent
                                                text: historyCard.modelData.category_label || (
                                                    historyCard.modelData.category === "war" ? qsTr("Chiến sự")
                                                    : historyCard.modelData.category === "tech" ? qsTr("Công nghệ")
                                                    : historyCard.modelData.category === "sports" ? qsTr("Bóng đá")
                                                    : historyCard.modelData.category === "viral" ? qsTr("Tin Lạ & Hài")
                                                    : historyCard.modelData.category === "hope" ? qsTr("Tin Vui")
                                                    : qsTr("Thời sự")
                                                )
                                                color: (historyCard.modelData.category === "war") ? "#FFB4AB"
                                                    : (historyCard.modelData.category === "tech") ? "#D6BBFB"
                                                    : (historyCard.modelData.category === "sports") ? "#8CE5B0"
                                                    : (historyCard.modelData.category === "viral") ? "#FFCCAA"
                                                    : (historyCard.modelData.category === "hope") ? "#A7F3D0"
                                                    : Theme.interactive
                                                font.pixelSize: TypeScale.metadata - 1
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        // YouTube Publication Status Badge
                                        Rectangle {
                                            implicitHeight: 20
                                            implicitWidth: ytBadgeRow.implicitWidth + 14
                                            radius: 10
                                            color: historyCard.modelData.youtube_published ? "#143324" : "#282932"
                                            border.width: 1
                                            border.color: historyCard.modelData.youtube_published ? "#27AE60" : Theme.outline

                                            RowLayout {
                                                id: ytBadgeRow
                                                anchors.centerIn: parent
                                                spacing: 4

                                                FluentIcon {
                                                    name: historyCard.modelData.youtube_published ? "success" : "share"
                                                    iconSize: 11
                                                    iconColor: historyCard.modelData.youtube_published ? "#2ECC71" : Theme.textMuted
                                                }

                                                Text {
                                                    text: historyCard.modelData.youtube_published ? qsTr("Đã đăng YouTube") : qsTr("Chưa đăng")
                                                    color: historyCard.modelData.youtube_published ? "#8CE5B0" : Theme.textMuted
                                                    font.pixelSize: TypeScale.metadata - 1
                                                    font.weight: Font.DemiBold
                                                }
                                            }
                                        }

                                        StatusBadge {
                                            status: "ready"
                                            label: historyCard.modelData.aspect_ratio || "16:9"
                                        }

                                        StatusBadge {
                                            status: "ready"
                                            label: (historyCard.modelData.scenes_count || 0) + qsTr(" tin")
                                        }

                                        StatusBadge {
                                            status: "ready"
                                            label: (historyCard.modelData.size_mb || 0) + " MB"
                                        }
                                    }

                                    // Time & Path info
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        Text {
                                            text: qsTr("Thời gian:")
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.metadata
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: historyCard.modelData.created_at || ""
                                            color: Theme.text
                                            font.pixelSize: TypeScale.metadata
                                            elide: Text.ElideRight
                                        }
                                    }

                                    // YouTube Link & Custom Note Row
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8
                                        visible: Boolean(historyCard.modelData.youtube_published || (historyCard.modelData.custom_note && historyCard.modelData.custom_note.length > 0))

                                        FluentIcon {
                                            name: historyCard.modelData.youtube_published ? "link" : "edit"
                                            iconSize: 13
                                            iconColor: historyCard.modelData.youtube_published ? "#2ECC71" : Theme.textMuted
                                        }

                                        Text {
                                            text: historyCard.modelData.youtube_published ? qsTr("YouTube:") : qsTr("Ghi chú:")
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.metadata
                                            font.weight: Font.DemiBold
                                        }

                                        Text {
                                            visible: Boolean(historyCard.modelData.youtube_url && historyCard.modelData.youtube_url.length > 0)
                                            text: historyCard.modelData.youtube_url || ""
                                            color: Theme.interactive
                                            font.pixelSize: TypeScale.metadata
                                            font.underline: ytLinkHover.hovered
                                            elide: Text.ElideMiddle
                                            Layout.maximumWidth: 320

                                            HoverHandler { id: ytLinkHover; cursorShape: Qt.PointingHandCursor }
                                            TapHandler {
                                                onTapped: {
                                                    if (controller && historyCard.modelData.youtube_url) {
                                                        controller.openExternalUrl(historyCard.modelData.youtube_url);
                                                    }
                                                }
                                            }
                                        }

                                        Text {
                                            visible: Boolean(historyCard.modelData.youtube_published_at && historyCard.modelData.youtube_published_at.length > 0)
                                            text: qsTr("(Đăng: %1)").arg(historyCard.modelData.youtube_published_at)
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.metadata
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            visible: Boolean(historyCard.modelData.custom_note && historyCard.modelData.custom_note.length > 0)
                                            text: qsTr("• Ghi chú: %1").arg(historyCard.modelData.custom_note)
                                            color: Theme.textMuted
                                            font.pixelSize: TypeScale.metadata
                                            elide: Text.ElideRight
                                        }
                                    }

                                    // Summary preview
                                    Text {
                                        Layout.fillWidth: true
                                        visible: Boolean(historyCard.modelData.summary && historyCard.modelData.summary.length > 0)
                                        text: historyCard.modelData.summary || ""
                                        color: Theme.textMuted
                                        font.pixelSize: TypeScale.control
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }

                                    // Action Buttons Row (Play, Folder, Custom Status, YouTube Direct, Delete)
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.space8

                                        StudioButton {
                                            text: qsTr("Xem video")
                                            iconName: "play"
                                            variant: "primary"
                                            compact: true
                                            onClicked: {
                                                if (controller) controller.openVideoFile(historyCard.modelData.video_path);
                                            }
                                        }

                                        StudioButton {
                                            text: qsTr("Mở thư mục")
                                            iconName: "folder"
                                            compact: true
                                            onClicked: {
                                                if (controller) controller.openOutputDir(historyCard.modelData.folder);
                                            }
                                        }

                                        StudioButton {
                                            text: qsTr("Kịch bản (.txt)")
                                            iconName: "text"
                                            compact: true
                                            onClicked: {
                                                if (controller) controller.openScriptForVideo(historyCard.modelData.video_path);
                                            }
                                        }

                                        // Custom YouTube Status Button
                                        StudioButton {
                                            text: historyCard.modelData.youtube_published ? qsTr("Sửa trạng thái YouTube") : qsTr("Đánh dấu YouTube")
                                            iconName: "edit"
                                            variant: "secondary"
                                            compact: true
                                            onClicked: {
                                                editStatusDialog.targetVideoPath = historyCard.modelData.video_path;
                                                editStatusDialog.targetTitle = historyCard.modelData.title || "";
                                                editStatusDialog.isPublished = Boolean(historyCard.modelData.youtube_published);
                                                editStatusDialog.youtubeUrl = historyCard.modelData.youtube_url || "";
                                                editStatusDialog.customNote = historyCard.modelData.custom_note || "";
                                                editStatusDialog.open();
                                            }
                                        }

                                        Item { Layout.fillWidth: true }

                                        // 1-Click Direct YouTube Publishing Button
                                        StudioButton {
                                            text: historyCard.modelData.youtube_published ? qsTr("Đăng lại YouTube") : qsTr("Đăng lên YouTube")
                                            iconName: "share"
                                            variant: "secondary"
                                            compact: true
                                            onClicked: {
                                                if (controller) controller.publishVideo(historyCard.modelData.video_path, "youtube");
                                            }
                                        }

                                        // Delete Video Button
                                        StudioButton {
                                            text: qsTr("Xóa video")
                                            iconName: "delete"
                                            variant: "danger"
                                            compact: true
                                            onClicked: {
                                                deleteConfirmDialog.targetVideoPath = historyCard.modelData.video_path;
                                                deleteConfirmDialog.targetTitle = historyCard.modelData.title || historyCard.modelData.video_name || "";
                                                deleteConfirmDialog.open();
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    // =========================================================================
    // CONFIRM DELETE VIDEO DIALOG
    // =========================================================================
    ConfirmDialog {
        id: deleteConfirmDialog
        property string targetVideoPath: ""
        property string targetTitle: ""

        title: qsTr("Xác nhận xóa bản tin")
        message: qsTr("Bạn có chắc chắn muốn xóa bản tin '%1' không?\n\nTệp video và dữ liệu liên quan sẽ bị xóa hoàn toàn khỏi máy tính.").arg(targetTitle)
        confirmText: qsTr("Xóa vĩnh viễn")
        confirmTone: "danger"

        onConfirmed: {
            if (controller && targetVideoPath) {
                controller.deleteVideo(targetVideoPath);
            }
        }
    }

    // =========================================================================
    // EDIT YOUTUBE STATUS & METADATA DIALOG
    // =========================================================================
    AppDialog {
        id: editStatusDialog
        property string targetVideoPath: ""
        property string targetTitle: ""
        property bool isPublished: false
        property string youtubeUrl: ""
        property string customNote: ""

        title: qsTr("Tùy chỉnh trạng thái đăng YouTube")
        preferredWidth: 520
        maximumWidth: 600

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                text: qsTr("Tiêu đề video YouTube (Bao gồm ngày tháng năm):")
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
            }

            AppTextField {
                id: editTitleField
                Layout.fillWidth: true
                text: editStatusDialog.targetTitle
                onTextChanged: editStatusDialog.targetTitle = text
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: Theme.divider
            }

            AppCheckBox {
                Layout.fillWidth: true
                text: qsTr("Đánh dấu đã đăng lên YouTube")
                checked: editStatusDialog.isPublished
                onCheckedChanged: editStatusDialog.isPublished = checked
            }

            Text {
                text: qsTr("Đường link video YouTube hoặc Video ID (Tùy chọn):")
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
            }

            AppTextField {
                id: editUrlField
                Layout.fillWidth: true
                placeholderText: "https://www.youtube.com/watch?v=... hoặc Video ID"
                text: editStatusDialog.youtubeUrl
                onTextChanged: editStatusDialog.youtubeUrl = text
            }

            Text {
                text: qsTr("Ghi chú / Tình hình thực tế (Tùy chọn):")
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
            }

            AppTextField {
                id: editNoteField
                Layout.fillWidth: true
                placeholderText: "Ví dụ: Đã đăng thủ công lúc 20:00, kênh phụ, bản Shorts..."
                text: editStatusDialog.customNote
                onTextChanged: editStatusDialog.customNote = text
            }
        }

        footerActions: [
            StudioButton {
                text: qsTr("Hủy")
                variant: "ghost"
                onClicked: editStatusDialog.reject()
            },
            StudioButton {
                text: qsTr("Lưu thay đổi")
                variant: "primary"
                onClicked: {
                    if (controller && editStatusDialog.targetVideoPath) {
                        controller.updateYouTubeStatus(
                            editStatusDialog.targetVideoPath,
                            editStatusDialog.isPublished,
                            editStatusDialog.youtubeUrl,
                            editStatusDialog.customNote,
                            "",
                            "",
                            editStatusDialog.targetTitle
                        );
                    }
                    editStatusDialog.accept();
                }
            }
        ]
    }
}