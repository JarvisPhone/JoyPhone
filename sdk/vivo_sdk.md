# vivo 企业开放 SDK API 文档

## 封面 / 修订历史

| 日期 | 版本号 | 修改内容 |
| --- | --- | --- |
| 2019/7/20 | v1.0 | 拟制 |
| 2019/11/05 | v1.1 | 修订部分API说明 |
| 2020/6/10 | v1.2 | 修订部分API说明 |
| 2020/12/10 | v2.0 | 新增API |
| 2021/11/25 | v3.0 | 新增API |
| 2022/8/8 | v3.1 | 修订部分API说明 |
| 2024/9/6 | v3.2 | 更新部分API参数说明 |
| 2024/11/29 | v3.3 | 增加部分接口方案及修改了 部分已知错误 |
| 2025/5/20 | V3.4 | 修改部分文档错误接口名， 补充了设置组织名称的前置 条件 |

## 1 概述

### 1.1 SDK 概览

vivo 企业开放SDK 目前共包含八大类管控，具体功能及实现类如下：

设备管理员：包含设备管理器、辅助服务、设备信息获取

- DeviceAdminManager
- DeviceAccessibilityManager
- DeviceInfoManager

应用管理：包含应用权限、应用运行状态、包管理、默认应用管理

- DeviceAppPermissionManager
- DeviceAppRunningManager
- DevicePackageManager
- DeviceApplicationManager

网络管理：包含APN 管理、VPN 管理、其他网络管理

- DeviceApnManager
- DeviceVpnManager
- DeviceNetworkManager

操作管理：包含按键管理、功能设置

- DeviceKeyEventManager
- DeviceOperationManager

外设管理：包含WLAN、蓝牙、USB、相机等各类外设管控

- DeviceWlanManager
- DeviceBluetoothManager
- DeviceUsbManager
- DevicePeripheralManager

通信管理：包含通话、短彩信、SIM 卡管理

- DeviceCallManager
- DeviceSmsManager
- DeviceTelecomManager

安全管理：包含设备ROOT 状态、锁屏密码等安全管控

- DeviceSecurityManager

用户管理：多用户功能管控

- DeviceUserManager

### 1.2 API 使用

需额外集成vivo 证书才能使用，证书申请方法见《vivo 企业开放SDK 开发指导》。

#### 1.2.1 权限声明

在app 的AndroidManifest.xml 文件添加如下权限：

```java
<uses-permission android:name="com.vivo.enterprise.permission.EMM"/>
```

该权限为使用vivo 企业开放SDK 的前置条件。

#### 1.2.2 注册设备管理器

所有API 必须依赖设备管理器才可使用。（设备管理器定义及开发可查阅Android 官方文档）

参考示例：（应用自定义及实现）

```java
<receiver
android:name="com.vivo.enterprise.DeviceAdminReceiver"
android:permission="android.permission.BIND_DEVICE_ADMIN" >
<meta-data
android:name="android.app.device_admin"
android:resource="@xml/device_admin" />
<intent-filter>
<action android:name="android.app.action.DEVICE_ADMIN_ENABLED" />
</intent-filter>
</receiver>
```

#### 1.2.3 API 调用

注意：如果使用的是市场公开版设备调试，安装开发证书应用后，需要重启一次设备，否则部

分功能无法初始化，导致调用API 无效。正式商用定制版本则无需此操作。

示例：

1. 首先必须激活vivo 设备管理器，才能使用其他API 接口

```java
import com.vivo.enterprise.VivoEnterpriseFactory;
import com.vivo.enterprise.admin.DeviceAdminManager;
//获得DeviceAdminManager 设备管理员类实例
//SDK 中所有的管控类实例都必须通过VivoEnterpriseFactory 获取
DeviceAdminManager mAdminManager= VivoEnterpriseFactory.getAdminManager();
//当前APK 的设备管理器组件名称
ComponentName mAdminName = new ComponentName(this, DeviceAdminReceiver.class);
//如果当前设备没有激活vivo 设备管理器，则先进行激活
if (mAdminManager != null && mAdminManager.getVivoAdmin() == null) {
mAdminManager.setVivoAdmin(mAdminName);
}
// 激活后使用其他管控API，需在证书申请对应权限
import com.vivo.enterprise.peripheral.DeviceBluetoothManager;
import com.vivo.enterprise.utils.Utils;
//获得DeviceBluetoothManager 蓝牙管理类实例
DeviceBluetoothManager mBluetoothManager = VivoEnterpriseFactory.getBluetoothManager();
//设置禁用蓝牙，vivo 设备管理器的组件名作为参数传入，需在证书申请蓝牙权限
mBluetoothManager.setBluetoothPolicy(mAdminName,Utils.RESTRICTION_POLICY_FORBIDDEN);
```

注：如果未激活vivo 设备管理器，调用任何管控API 都会抛出异常。如未申请对应接口功能权

限，调用该类管控API 都会抛出异常。

#### 1.2.4 获取SDK 支持信息

在使用API 之前，可使用getSdkInfo 接口获取本设备支持企业开放SDK 的情况，此接口调用无

需证书和权限。

```java
import com.vivo.enterprise.VivoEnterpriseFactory;
import com.vivo.enterprise.admin. DeviceInfoManager;
DeviceInfoManager mDeviceInfoManager= VivoEnterpriseFactory. getDeviceInfoManager();
ComponentName mAdminName = new ComponentName(this, DeviceAdminReceiver.class);
String info = mDeviceInfoManager. getSdkInfo(mAdminName);
```

info 信息包含：

sdkersion:当前设备支持的SDK 版本号

customname:客户名称/定制信息（商业证书体现）

available:应用是否有权调用SDK（当前vivo 证书是否已生效，false 表示证书有问题）

不支持的设备返回UnKnown。

## 2 API 详解

本章详细介绍SDK 所有API 功能，请结合JavaDoc 文档使用。

### 2.1 设备管理员类（DeviceAdminManager）

#### 2.1.1 vivo 设备管理器

**boolean setVivoAdmin(ComponentName admin);**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setVivoAdmin(ComponentName admin);` |
| 功能描述 | 激活vivo 设备管理器，是使用SDK 的前提，激活成功后才可使用其他API 功能。激<br>活后应用无法卸载，拥有设备最高权限。需申请vivo 证书后才可使用该接口，证书申<br>请流程详见《vivo 企业开放SDK 开发指导》 |
| 参数 | admin：设备管理器组件名（本文档中所有该参数，如无特殊说明，均指vivo 设备管 理器组件名） 例：ComponentName admin = new `ComponentName("com.example.packageName","com.example.packageName.AdminReceiver");` |
| 返回值 | true 激活成功；false 激活失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setVivoAdmin(admin);` |

**boolean removeVivoAdmin (ComponentName admin);**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean removeVivoAdmin (ComponentName admin);` |
| 功能描述 | 取消激活vivo 设备管理器，所有SDK 管控功能失效 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true 取消激活成功；false 取消激活失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().removeVivoAdmin(admin);` |

**ComponentName getVivoAdmin ();**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getVivoAdmin ();` |
| 功能描述 | 获取当前激活的vivo 设备管理器组件名 |
| 参数 | 无 |
| 返回值 | ComponentName 组件名，不存在时返回null |
| 使用示例 | `ComponentName admin = VivoEnterpriseFactory.getAdminManager().getVivoAdmin();` |

#### 2.1.2 普通设备管理器

> 需要权限：设备所有者管理

**boolean setDeviceAdmin(ComponentName admin, ComponentName admin2,boolean isActive)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDeviceAdmin(ComponentName admin, ComponentName admin2,boolean isActive)` |
| 功能描述 | 激活/取消普通设备管理器，成为vivo 设备管理器后无需再激活，激活其他应用使用 |
| 参数 | admin：vivo 设备管理器组件名；admin2 普通设备管理器组件名；<br>isActive：激活true/取消激活false |
| 返回值 | true/false 成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setDeviceAdmin(admin, admin2,isActive);` |

**boolean setActiveDeviceAdminPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setActiveDeviceAdminPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止激活普通设备管理器 |
| 参数 | admin：vivo 设备管理器组件名<br>policy：允许激活普通设备管理器Utils.RESTRICTION_POLICY_DEFAULT = 0 禁止激活普通设备管理器Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true 允许/禁止激活普通设备管理器成功；false 允许/禁止激活普通设备管理器失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setActiveDeviceAdminPolicy(admin,policy);` |

**int getActiveDeviceAdminPolicy (ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getActiveDeviceAdminPolicy (ComponentName admin)` |
| 功能描述 | 获取是否允许激活普通设备管理器策略 |
| 参数 | admin：vivo 设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁止：Utils.RESTRICTION_POLICY_ FORBIDDEN= 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAdminManager().getActiveDeviceAdminPolicy(admin);` |

#### 2.1.3 DeviceOwner

> 需要权限：设备所有者管理

**boolean setDeviceOwner(ComponentName admin, String ownerName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDeviceOwner(ComponentName admin, String ownerName)` |
| 功能描述 | 设置DeviceOwner（可设置vivo 设备管理器或任意设备管理器为DeviceOwner，注<br>意设置后应用分身功能将无法使用） |
| 参数 | admin：要设置DeviceOwner 的组件名<br>ownerName：设备拥有者名称（自定义） 例：String ownerName = "admin"; |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setDeviceOwner(admin,ownerName);` |

**void clearDeviceOwner (String packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void clearDeviceOwner (String packageName)` |
| 功能描述 | 清除DeviceOwner （注：如vivo 设备管理器为DeviceOwner，清除时会同时取消激<br>活vivo 设备管理器） |
| 参数 | packageName：已设置DeviceOwner 的包名 例：String packageName = "com.example.packageName"; |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAdminManager().clearDeviceOwner(packageName);` |

**ComponentName getDeviceOwner()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDeviceOwner()` |
| 功能描述 | 获取DeviceOwner 组件名 |
| 参数 | 无 |
| 返回值 | `ComponentName`<br>当前DeviceOwner 组件名，不存在时返回null |
| 使用示例 | `ComponentName name = VivoEnterpriseFactory.getAdminManager().getDeviceOwner();` |

**String getDeviceOwnerName()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getDeviceOwnerName()` |
| 功能描述 | 获取DeviceOwner 应用名（即桌面显示的名称） |
| 参数 | 无 |
| 返回值 | `String`<br>当前DeviceOwner 应用名称，不存在时返回null |
| 使用示例 | `String name = VivoEnterpriseFactory.getAdminManager().getDeviceOwnerName()` |

**int getDeviceOwnerUserId()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDeviceOwnerUserId()` |
| 功能描述 | 获取DeviceOwner 存在于哪个用户 |
| 参数 | 无 |
| 返回值 | int<br>DeviceOwner 所在用户ID，不存在时返回-1 |
| 使用示例 | `int userId = VivoEnterpriseFactory.getAdminManager().getDeviceOwnerUserId()` |

**boolean setDeviceOwnerPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDeviceOwnerPolicy(ComponentName admin, int policy)` |
| 功能描述 | 管控是否允许设置DeviceOwner |
| 参数 | admin：设备管理器组件名<br>policy：允许设置DeviceOwner：Utils.RESTRICTION_POLICY_DEFAULT = 0 不允许设置DeviceOwner：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false<br>设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setDeviceOwnerPolicy(admin, policy);` |

**int getDeviceOwnerPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDeviceOwnerPolicy(ComponentName admin)` |
| 功能描述 | 获取是否允许设置DeviceOwner 状态 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>禁止/允许<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁止：Utils.RESTRICTION_POLICY_ FORBIDDEN= 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAdminManager().getDeviceOwnerPolicy(admin);` |

**setOrganizationName(ComponentName admin, CharSequence deviceOwnerInfo)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `setOrganizationName(ComponentName admin, CharSequence deviceOwnerInfo)` |
| 功能描述 | 修改锁屏显示的管控单位名称（前置条件：DeviceOwner 存在，必须提前设置<br>DeviceOwner 才可修改管控单位名称） |
| 参数 | admin：DeviceOwner 或ProfileOwner 组件名<br>deviceOwnerInfo：单位名称，例：CharSequence deviceOwnerInfo = "Company `Name";` |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAdminManager().setOrganizationName(admin, deviceOwnerInfo);` |

**CharSequence getOrganizationName()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `CharSequence getOrganizationName()` |
| 功能描述 | 获取锁屏显示的管控单位名称（DeviceOwner 或ProfileOwner 存在时） |
| 参数 | 无 |
| 返回值 | CharSequence 单位名称字符 |
| 使用示例 | `CharSequence name = VivoEnterpriseFactory.getAdminManager().getOrganizationName();` |

#### 2.1.4 ProfileOwner

> 需要权限：设备所有者管理

**boolean setProfileOwner(ComponentName admin, String ownerName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setProfileOwner(ComponentName admin, String ownerName)` |
| 功能描述 | 设置ProfileOwner （可设置vivo 设备管理器或任意设备管理器为ProfileOwner） |
| 参数 | admin：ProfileOwner 组件名<br>ownerName：Profile 拥有者名称（自定义）例：String ownerName = "admin"; |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAdminManager().setProfileOwner(admin, ownerName);` |

**void clearProfileOwner(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void clearProfileOwner(ComponentName admin)` |
| 功能描述 | 清除ProfileOwner（注：如vivo 设备管理器为ProfileOwner，清除时会同时取消激活<br>vivo 设备管理器） |
| 参数 | admin：ProfileOwner 组件名 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAdminManager().clearProfileOwner(admin);` |

**ComponentName getProfileOwner()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getProfileOwner()` |
| 功能描述 | 获取ProfileOwner 组件名 |
| 参数 | 无 |
| 返回值 | `ComponentName`<br>当前ProfileOwner 组件名，不存在时返回null |
| 使用示例 | `ComponentName admin = VivoEnterpriseFactory.getAdminManager().getProfileOwner();` |

**String getProfileOwnerName ()**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getProfileOwnerName ()` |
| 功能描述 | 获取ProfileOwner 应用名（即桌面显示的名称） |
| 参数 | 无 |
| 返回值 | `String`<br>当前ProfileOwner 应用名称，不存在时返回null |
| 使用示例 | `String name = VivoEnterpriseFactory.getAdminManager().getProfileOwnerName();` |

**boolean setProfileOwnerPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setProfileOwnerPolicy(ComponentName admin, int policy)` |
| 功能描述 | 管控是否允许设置ProfileOwner |
| 参数 | admin：设备管理器组件名<br>policy：允许设置ProfileOwner：Utils.RESTRICTION_POLICY_DEFAULT = 0 不允许设置ProfileOwner：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false<br>设置成功/失败 |
| 使用示例 | `int result = VivoEnterpriseFactory.getAdminManager().setProfileOwnerPolicy(admin, policy);` |

**int getProfileOwnerPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getProfileOwnerPolicy(ComponentName admin)` |
| 功能描述 | 获取是否允许设置ProfileOwner 状态 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>禁止/允许<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁止：Utils.RESTRICTION_POLICY_ FORBIDDEN= 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAdminManager().getProfileOwnerPolicy(admin);` |

### 2.2 辅助服务管理类（DeviceAccessibilityManager）

#### 2.2.1 开启/关闭辅助服务

> 需要权限：辅助功能管理

**boolean setAccessibilityServcie(ComponentName admin, ComponentNamecomponentName, boolean isActive)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAccessibilityServcie(ComponentName admin, ComponentNamecomponentName, boolean isActive)` |
| 功能描述 | 开启/关闭辅助服务，开启后设置下该辅助服务项不可操作，用户无法手动关闭。注意<br>辅助服务的包应该设置为常驻保活，否则被杀死后辅助服务会强制关闭 |
| 参数 | admin：vivo 设备管理器组件名<br>componentName：辅助服务组件名<br>isActive：开启/ 关闭 |
| 返回值 | true/false 开启成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAccessibilityManager().setAccessibilityServcie(admin,componentName, isActive);` |

**List<ComponentName> getAccessibilityServcie(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<ComponentName> getAccessibilityServcie(ComponentName admin)` |
| 功能描述 | 获取当前已开启的辅助服务列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `List<ComponentName>`<br>已开启的辅助服务组件列表，不存在时返回null |
| 使用示例 | `List<ComponentName> accessibilityServcie = VivoEnterpriseFactory.getAccessibilityManager().getAccessibilityServcie(admin);` |

#### 2.2.2 设置允许的辅助服务

> 需要权限：辅助功能管理

**boolean setPermittedAccessibilityServices(ComponentName admin, List<String>`<br>packageList)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPermittedAccessibilityServices(ComponentName admin, List<String>`<br>packageList) |
| 功能描述 | 设置允许的辅助服务包名列表，未添加到列表的辅助服务将无法开启（系统辅助服务<br>除外） |
| 参数 | admin：设备管理器组件名<br>packageList：辅助服务包名列表，为空则清除设置，例： `List<String> packageList = new ArrayList<>();` `packageList.add("com.example.packageName");` |
| 返回值 | true/false 开启成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAccessibilityManager().setPermittedAccessibilityServices(admin,packageList);` |

**List<String> getPermittedAccessibilityServices(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getPermittedAccessibilityServices(ComponentName admin)` |
| 功能描述 | 获取允许的辅助服务包名列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 辅助服务包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAccessibilityManager().getPermittedAccessibilityServices(admin);` |

**List<String> getPermittedAccessibilityServicesForUser(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getPermittedAccessibilityServicesForUser(ComponentName admin)` |
| 功能描述 | 获取允许的辅助服务包名列表，包括系统辅助服务 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 辅助服务包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAccessibilityManager().getPermittedAccessibilityServicesForUser(admin);` |

**boolean isAccessibilityServicePermittedByAdmin(ComponentName admin, String`<br>packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean isAccessibilityServicePermittedByAdmin(ComponentName admin, String`<br>packageName) |
| 功能描述 | 判断是否为允许的辅助服务包名 |
| 参数 | admin：设备管理器组件名<br>packageName：包名，例：String packageName = "com.example.packageName"; |
| 返回值 | true/false 允许的辅助服务/禁止的辅助服务 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAccessibilityManager().isAccessibilityServicePermittedByAdmin(admin,packageName);` |

### 2.3 设备信息获取类（DeviceInfoManager）

#### 2.3.1 获取系统版本号

**String getRomVersion(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getRomVersion(ComponentName admin)` |
| 功能描述 | 获取当前系统软件版本号 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | String 版本号，获取失败返回unKnown |
| 使用示例 | `String version = VivoEnterpriseFactory.getDeviceInfoManager().getRomVersion(admin);` |

#### 2.3.2 获取设备信息

**String getDeviceInfo(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getDeviceInfo(ComponentName admin)` |
| 功能描述 | 获取设备信息，包括RAM、ROM、屏幕分辨率、厂商、内核版本、软件版本等 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `String`<br>设备信息，获取失败返回unKnown |
| 使用示例 | `String deviceInfo= VivoEnterpriseFactory.getDeviceInfoManager().getDeviceInfo(admin);` |

#### 2.3.3 获取SDK 信息

**String getSdkInfo(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getSdkInfo(ComponentName admin)` |
| 功能描述 | 获取sdk 版本号、定制项目信息、当前应用集成的vivo 证书是否有效 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `String`<br>sdk 信息，获取失败返回unKnown |
| 使用示例 | `String sdkInfo= VivoEnterpriseFactory.getDeviceInfoManager().getSdkInfo(admin);` |

### 2.4 应用权限管理类（DeviceAppPermissionManager）

#### 2.4.1 应用运行时权限策略

> 需要权限：应用权限管理

**void setPermissionPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setPermissionPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用运行时权限默认响应策略（全局策略，设置后，所有新安装的应用申请动态<br>权限时，默认按设置的策略处理，除特殊需求外，一般不建议使用） |
| 参数 | admin：设备管理器组件名<br>policy：默认/自动允许/自动拒绝<br>policy：总是询问：Utils.RESTRICTION_POLICY_DEFAULT = 0 自动允许：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 自动拒绝：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAppPermissionManager().setPermissionPolicy(admin, policy);` |

**int getPermissionPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPermissionPolicy(ComponentName admin)` |
| 功能描述 | 获取应用运行时权限默认响应策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>总是询问：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>自动允许：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>自动拒绝：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAppPermissionManager().getPermissionPolicy(admin);` |

#### 2.4.2 应用权限白名单

> 需要权限：应用权限管理

**boolean addAppPermissionWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppPermissionWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用权限白名单，白名单内的应用默认打开所有基础动态权限，无需弹框请求用<br>户允许，且用户无法在设置权限列表里手动关闭权限（注：包含了开机自启动权限，<br>应用可监听开机广播自启） |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppPermissionWhiteList(admin, pkgs);` |

**List<String> getAppPermissionWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppPermissionWhiteList(ComponentName admin)` |
| 功能描述 | 获取应用权限白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 权限白名单应用包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppPermissionWhiteList(admin);` |

**boolean deleteAppPermissionWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppPermissionWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用权限白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需要删除的白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppPermissionWhiteList(admin, pkgs);` |

**boolean clearAppPermissionWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppPermissionWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用权限白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppPermissionWhiteList(admin);` |

#### 2.4.3 应用Alarm 白名单

> 需要权限：应用精确闹钟权限

**boolean addAppAlarmWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppAlarmWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加Alarm 白名单，白名单内的应用不受系统Alarm 对齐限制（注：除MDM 自身外<br>只可添加证书申请时填写的关联应用，未加入证书关联名单的应用无法添加成功）<br>因Alarm 频繁唤醒会严重影响耗电，加入白名单的应用需要严格控制唤醒时间间隔 |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppAlarmWhiteList(admin, pkgs);` |

**List<String> getAppAlarmWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppAlarmWhiteList(ComponentName admin)` |
| 功能描述 | 获取Alarm 白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> Alarm 白名单应用包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppAlarmWhiteList(admin);` |

**boolean deleteAppAlarmWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppAlarmWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除Alarm 白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需要删除的白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppAlarmWhiteList(admin, pkgs);` |

**boolean clearAppAlarmWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppAlarmWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空Alarm 白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppAlarmWhiteList(admin);` |

#### 2.4.4 应用移动数据网络黑白名单策略

> 需要权限：应用权限管理

**boolean setAppMeteredDataPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppMeteredDataPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用移动数据网络黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名<br>单列表中的应用不可连接数据网络，白名单模式下，白名单应用强制打开数据网络权<br>限且不可关闭，白名单模式2 下，白名单2 列表之外的应用不可使用数据网络<br>(Android12 及以上才支持白名单模式2) |
| 参数 | admin：设备管理器组件名<br>policy：普通模式：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 白名单模式2：Utils.RESTRICTION_POLICY_WHITELIST_TWO = 15 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().setAppMeteredDataPolicy(admin, policy);` |

**int getAppMeteredDataPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppMeteredDataPolicy(ComponentName admin)` |
| 功能描述 | 获取应用移动数据网络黑白名单模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>普通模式：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4<br>白名单模式2：Utils.RESTRICTION_POLICY_WHITELIST_TWO = 15 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAppPermissionManager().getAppMeteredDataPolicy(admin);` |

#### 2.4.5 应用移动数据网络黑白名单列表

> 需要权限：应用权限管理

**boolean addAppMeteredDataBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppMeteredDataBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用移动数据网络黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名<br>单列表中的应用不可连接数据网络（注：只可添加三方应用+部分系统应用，同i 管家<br>联网管理列表一致） |
| 参数 | admin：设备管理器组件名<br>pkgs：黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppMeteredDataBlackList(admin, pkgs);` |

**List<String> getAppMeteredDataBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppMeteredDataBlackList(ComponentName admin)` |
| 功能描述 | 获取应用移动数据网络黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppMeteredDataBlackList(admin);` |

**boolean deleteAppMeteredDataBlackList(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppMeteredDataBlackList(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除应用移动数据网络黑名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppMeteredDataBlackList(admin,pkgs);` |

**boolean clearAppMeteredDataBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppMeteredDataBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用移动数据网络黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppMeteredDataBlackList(admin);` |

**boolean addAppMeteredDataWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppMeteredDataWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用移动数据网络白名单列表，需配合黑白名单策略使用。白名单模式下，白名<br>单应用强制打开数据网络权限且不可关闭（注：只可添加三方应用+部分系统应用，同<br>i 管家联网管理列表一致） |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppMeteredDataWhiteList(admin, pkgs);` |

**List<String> getAppMeteredDataWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppMeteredDataWhiteList(ComponentName admin)` |
| 功能描述 | 获取应用移动数据网络白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppMeteredDataWhiteList(admin);` |

**boolean deleteAppMeteredDataWhiteList(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppMeteredDataWhiteList(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除应用移动数据网络白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppMeteredDataWhiteList(admin,pkgs);` |

**boolean clearAppMeteredDataWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppMeteredDataWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用移动数据网络白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppMeteredDataWhiteList(admin, pkgs);` |

**boolean addAppMeteredDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppMeteredDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持) |
| 功能描述 | 添加应用移动数据网络白名单2 列表，需配合黑白名单策略使用。白名单模式2 下，<br>白名单2 应用列表之外的应用不可使用数据网络 |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单2 应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppMeteredDataWhiteListTwo(admin,pkgs);` |

**List<String> getAppMeteredDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppMeteredDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取应用移动数据网络白名单2 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单2 应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppMeteredDataWhiteListTwo(admin);` |

**boolean deleteAppMeteredDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppMeteredDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持) |
| 功能描述 | 删除应用移动数据网络白名单2 列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的白名单2 应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppMeteredDataWhiteListTwo(admin,pkgs);` |

**boolean clearAppMeteredDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppMeteredDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用移动数据网络白名单2 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppMeteredDataWhiteListTwo(admin);` |

#### 2.4.6 应用WLAN 网络黑白名单策略

> 需要权限：应用权限管理

**boolean setAppWlanDataPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppWlanDataPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用WLAN 网络黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单<br>列表中的应用不可连接WLAN，白名单模式下，白名单应用强制打开WLAN 网络权限<br>且不可关闭，白名单模式2 下，白名单2 列表之外的应用不可使用WLAN 网络<br>(Android12 及以上才支持白名单模式2) |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式/白名单模式2<br>policy：普通模式：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 白名单模式2：Utils.RESTRICTION_POLICY_WHITELIST_TWO = 15 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().setAppWlanDataPolicy(admin, policy);` |

**int getAppWlanDataPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppWlanDataPolicy(ComponentName admin)` |
| 功能描述 | 获取应用WLAN 网络黑白名单模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>普通模式：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4<br>白名单模式2：Utils.RESTRICTION_POLICY_WHITELIST_TWO = 15 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAppPermissionManager().getAppWlanDataPolicy(admin);` |

#### 2.4.7 应用WLAN 网络黑白名单列表

> 需要权限：应用权限管理

36

**boolean addAppWlanDataBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppWlanDataBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用WLAN 网络黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单<br>列表中的应用不可连接WLAN（注：只可添加三方应用+i 音乐） |
| 参数 | admin：设备管理器组件名<br>pkgs：黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppWlanDataBlackList(admin, pkgs);` |

**List<String> getAppWlanDataBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppWlanDataBlackList(ComponentName admin)` |
| 功能描述 | 获取应用WLAN 网络黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppWlanDataBlackList(admin);` |

**boolean deleteAppWlanDataBlackList (ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppWlanDataBlackList (ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用WLAN 网络黑名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppWlanDataBlackList(admin, pkgs);` |

**boolean clearAppWlanDataBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppWlanDataBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用WLAN 网络黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppWlanDataBlackList(admin);` |

**boolean addAppWlanDataWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppWlanDataWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用WLAN 网络白名单列表，需配合黑白名单策略使用。白名单模式下，白名单<br>应用强制打开WLAN 网络权限且不可关闭（注：只可添加三方应用+i 音乐） |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppWlanDataWhiteList(admin, pkgs);` |

**List<String> getAppWlanDataWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppWlanDataWhiteList(ComponentName admin)` |
| 功能描述 | 获取应用WLAN 网络白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppWlanDataWhiteList(admin);` |

**boolean deleteAppWlanDataWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppWlanDataWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用WLAN 网络白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppWlanDataWhiteList(admin, pkgs);` |

**boolean clearAppWlanDataWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppWlanDataWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用WLAN 网络白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppWlanDataWhiteList(admin);` |

**boolean addAppWlanDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppWlanDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持) |
| 功能描述 | 添加应用WLAN 网络白名单2 列表，需配合黑白名单策略使用。白名单模式2 下，白<br>名单2 列表之外的应用不可使用数据网络 |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单2 应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().addAppWlanDataWhiteListTwo(admin, pkgs);` |

**List<String> getAppWlanDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppWlanDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取应用WLAN 网络白名单2 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单2 应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppPermissionManager().getAppWlanDataWhiteListTwo(admin);` |

**boolean deleteAppWlanDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppWlanDataWhiteListTwo(ComponentName admin, List<String>`<br>pkgs)<br>(Android12 及以上支持) |
| 功能描述 | 删除应用WLAN 网络白名单2 列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的白名单2 应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().deleteAppWlanDataWhiteListTwo(admin,pkgs);` |

**boolean clearAppWlanDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppWlanDataWhiteListTwo(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用WLAN 网络白名单2 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppPermissionManager().clearAppWlanDataWhiteListTwo(admin);` |

### 2.5 应用运行管理类（DeviceAppRunningManager）

#### 2.5.1 杀死进程

> 需要权限：应用运行状态管理

**boolean killProcess(ComponentName admin, List<String> procNames)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean killProcess(ComponentName admin, List<String> procNames)` |
| 功能描述 | 杀死指定进程 |
| 参数 | admin：设备管理器组件名<br>procNames：指定进程名列表，例： `List<String> procNames= new ArrayList<>();` `procNames.add("com.example.processName");` |
| 返回值 | true/false 杀死成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().killProcess(admin, list);` |

#### 2.5.2 获取正在运行进程

> 需要权限：应用运行状态管理

**List<RunningAppProcessInfo> getRunningAppProcesses(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<RunningAppProcessInfo> getRunningAppProcesses(ComponentName admin)` |
| 功能描述 | 获取当前正在运行的进程信息（系统核心进程除外） |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<RunningAppProcessInfo> 进程信息列表，不存在时返回null |
| 使用示例 | `List<ActivityManager.RunningAppProcessInfo> listRun = VivoEnterpriseFactory.getAppRunningManager().getRunningAppProcesses(admin);` |

#### 2.5.3 停止指定包

> 需要权限：应用运行状态管理

**boolean forceStopPackage(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean forceStopPackage(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 停止指定包名应用下的所有进程 |
| 参数 | admin：设备管理器组件名<br>pkgs：指定包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 停止成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().forceStopPackage(admin, list);` |

#### 2.5.4 清除后台进程

> 需要权限：应用运行状态管理

**boolean clearBackgroundApps(ComponentName admin, boolean includeLock)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearBackgroundApps(ComponentName admin, boolean includeLock)` |
| 功能描述 | 清除后台所有进程（一键加速） |
| 参数 | admin：设备管理器组件名<br>includeLock：是否清除用户锁定在任务列表的进程 |
| 返回值 | true/false 清除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().clearBackgroundApps(admin,includeLock);` |

#### 2.5.5 禁用应用组件

> 需要权限：应用运行状态管理

**boolean setComponentEnabledSetting(ComponentName admin,List<ComponentName> componentNames, int newState)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setComponentEnabledSetting(ComponentName admin,List<ComponentName> componentNames, int newState)` |
| 功能描述 | 禁用应用内某个组件，禁用后无法启动该组件（系统核心程序不允许禁用） |
| 参数 | admin：设备管理器组件名<br>componentNames：组件名<br>newState：禁用状态 0：恢复默认 1：启用组件 2：禁用组件 3：用户禁止启动该应用 4：用户实际 使用它，该程序才会被启动 |
| 返回值 | true/false 禁用成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().setComponentEnabledSetting(admin,componentNames, newState);` |

#### 2.5.6 禁用应用

> 需要权限：应用运行状态管理

**boolean addDisabledAppList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addDisabledAppList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 禁用应用，应用在桌面或菜单消失，无法打开（系统核心程序不允许禁用） |
| 参数 | admin：设备管理器组件名<br>pkgs：禁用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` 注：某些系统应用无法被禁用 |
| 返回值 | true/false 禁用成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().addDisabledAppList(admin,pkgs);` |

**List<String> getDisabledAppList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getDisabledAppList(ComponentName admin)` |
| 功能描述 | 获取已被禁用应用的包名列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 应用包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppRunningManager().getDisabledAppList(admin);` |

**boolean deleteDisabledAppList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteDisabledAppList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除禁用应用列表，应用会重新可用 |
| 参数 | admin：设备管理器组件名<br>pkgs：需被删除的已禁用应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().deleteDisabledAppList(admin,pkgs);` |

**boolean clearDisabledAppList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearDisabledAppList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空禁用应用列表，应用会重新可用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().clearDisabledAppList(admin);` |

#### 2.5.7 禁止启动应用

> 需要权限：应用运行状态管理

**boolean addDisallowedLaunchAppList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addDisallowedLaunchAppList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 禁止启动，挂起应用，应用图标仍会显示在桌面，但无法点击启动，应用通知会被隐<br>藏，且不会显示任何提示及声音，系统核心程序不允许禁止 |
| 参数 | admin：设备管理器组件名<br>pkgs：禁止包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 禁止成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().addDisallowedLaunchAppList(admin, pkgs);` |

**List<String> getDisallowedLaunchAppList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getDisallowedLaunchAppList(ComponentName admin)` |
| 功能描述 | 获取已被禁止启动应用的包名列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 应用包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppRunningManager().getDisallowedLaunchAppList(admin);` |

**boolean deleteDisallowedLaunchAppList(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteDisallowedLaunchAppList(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除禁止启动应用列表，应用恢复可启用状态 |
| 参数 | admin：设备管理器组件名<br>pkgs：需被删除的已禁用应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().deleteDisallowedLaunchAppList(admin, pkgs);` |

**boolean clearDisallowedLaunchAppList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearDisallowedLaunchAppList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空禁止启动应用列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().clearDisallowedLaunchAppList(admin);` |

#### 2.5.8 常驻保活应用

> 需要权限：应用运行状态管理

**boolean addPersistentAppList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addPersistentAppList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用为常驻应用，可后台保活不被杀死，包括近期任务防杀、低内存防杀，进程<br>意外停止会自动拉起，开机自动拉起进程（注：意外被杀只会重新拉起进程而非主界<br>面，且除MDM 应用自身外，只可添加证书中填写的关联应用，未加入证书关联名单<br>的应用无法保活） |
| 参数 | admin：设备管理器组件名<br>pkgs：常驻包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().addPersistentAppList(admin,pkgs);` |

**List<String> getPersistentAppList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getPersistentAppList(ComponentName admin)` |
| 功能描述 | 获取已添加的常驻应用包名列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 应用包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getAppRunningManager().getPersistentAppList(admin);` |

**boolean deletePersistentAppList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deletePersistentAppList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除常驻应用列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需被删除的常驻应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().deletePersistentAppList(admin,pkgs);` |

**boolean clearPersistentAppList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearPersistentAppList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空常驻应用列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().clearPersistentAppList(admin);` |

#### 2.5.9 锁定应用

47

> 需要权限：应用运行状态管理

**void setLockTaskPackages(ComponentName admin, String[] packages)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setLockTaskPackages(ComponentName admin, String[] packages)` |
| 功能描述 | 添加可被锁定（霸屏）的应用列表，被锁定后的应用无法退出，无法跳转其他应用，<br>即只能在设置的应用列表内活动，需配合接口setLockTaskFeatures（设置锁定模式）<br>和startLockApp（锁定应用）使用（注：锁定的应用建议设为常驻保活，一旦被后台<br>杀死，锁定即刻失效，重启也会失效） |
| 参数 | admin：设备管理器组件名<br>packages：可被锁定的应用包名列表，例： `String[] packages = {"com.example.packageName"};` |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAppRunningManager().setLockTaskPackages(admin, packages);` |

**String[] getLockTaskPackages(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String[] getLockTaskPackages(ComponentName admin)` |
| 功能描述 | 获取可被锁定的应用包名列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | String[] 应用包名数组，不存在时返回null |

**boolean isLockTaskPermitted(String pkg)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean isLockTaskPermitted(String pkg)` |
| 功能描述 | 判断指定包名的应用是否允许被锁定 |
| 参数 | pkg：包名 |
| 返回值 | true/false 允许/禁止 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().isLockTaskPermitted(pkg);` |

**void setLockTaskFeatures(ComponentName admin, int flags)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setLockTaskFeatures(ComponentName admin, int flags)` |
| 功能描述 | 设置锁定模式，需配合setLockTaskPackages 使用 |
| 参数 | admin：设备管理器组件名<br>flags：锁定模式，参数含义如下 0：锁定后禁用系统界面其他所有操作，包括状态栏信息，通知，上滑快捷面板，关机 面板，锁屏 1：只启用状态栏的系统信息，其他均不可用 16：只启用长按关机面板，其他均不可用 32：只启用锁屏，其他均不可用 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getAppRunningManager().setLockTaskFeatures(admin, flags);` |

**int getLockTaskFeatures(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getLockTaskFeatures(ComponentName admin)` |
| 功能描述 | 获取当前的锁定模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 锁定模式，参数含义如下<br>0：锁定后禁用系统界面其他所有操作，包括状态栏信息，通知，上滑快捷面板，关机<br>面板，锁屏<br>1：只启用状态栏的系统信息，其他均不可用<br>16：只启用长按关机面板，其他均不可用<br>32：只启用锁屏，其他均不可用 |
| 使用示例 | `int flags = VivoEnterpriseFactory.getAppRunningManager().getLockTaskFeatures(admin);` |

**boolean startLockApp(ComponentName admin, boolean isLock)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean startLockApp(ComponentName admin, boolean isLock)` |
| 功能描述 | 立即锁定应用，锁定后按返回键也无法退出应用，需使用setLockTaskPackages 添加<br>到列表方可锁定，应用被锁定时必须处于前台界面，处于后台无法锁定。 |
| 参数 | admin：设备管理器组件名<br>isLock：true/false 锁定/取消锁定 |
| 返回值 | int 锁定模式 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().startLockApp(admin, isLock);` |

#### 2.5.10 获取顶层应用

> 需要权限：应用运行状态管理

**String getTopAppPackage(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getTopAppPackage(ComponentName admin)` |
| 功能描述 | 获取顶层应用包名 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | string 包名 |
| 使用示例 | `String topAppPackage = VivoEnterpriseFactory.getAppRunningManager().getTopAppPackage(admin);` |

#### 2.5.11 定制设置菜单

> 需要权限：应用运行状态管理

**boolean setCustomSettingsMenu(ComponentName admin, List<String>`<br>deleteMenus)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setCustomSettingsMenu(ComponentName admin, List<String>`<br>deleteMenus) |
| 功能描述 | 定制设置菜单，可以隐藏设置中任意一级菜单（仅支持对设置主界面的一级菜单隐藏，<br>不支持从其他应用进入到此一级菜单内部）。<br>注：需要重启“设置”应用后才生效。 |
| 参数 | admin：设备管理器组件名<br>deleteMenus：隐藏菜单列表，请查看下方各菜单对应参数值，为null 则还原初始状态 （注：隐藏任意菜单会同时隐藏设置搜索栏） {"登陆vivo 账号":"vivo_account", "我的设备":"device_info", "飞行模式":"airplane_mode", "WLAN":"wifi", "移动网络":"mobile_network", "其他网络与连接":"extra_network_connection", "通知 与状态栏":"notifications", "显示与亮度":"display_brightness", "桌面、锁屏与壁纸":"theme", "动态效 果":"dynamic_effect", "声音与振动":"sounds_vibration", "jovi":"jovi", "系统导航":"navigation", "指纹、 面部与密码":"fingerpint_face_password", "游戏魔盒":"game_cube", "快捷与辅助 ":"shortcuts_accessibility", "系统管理":"system_management", "安全与隐私":"security_privacy", "屏 幕使用时间":"screen_time", "运存与存储空间":"storage", "电池":"battery", "应用与权限 ":"application_permission", "google":"google", "账号与同步":"account_sync"} 如隐藏“我的设备”与“飞行模式”两个菜单： `List<String> deleteMenus = new ArrayList<>();` `deleteMenus.add("device_info");deleteMenus.add("airplane_mode");` |
| 返回值 | true/false 成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().setCustomSettingsMenu(admin, deleteMenus);` |

#### 2.5.12 允许/禁止应用加密与隐藏

> 需要权限：操作行为管理

**boolean setAppEncryptionAndHidePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppEncryptionAndHidePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 禁止应用加密和应用迁移隐藏功能 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁用<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getAppRunningManager().setAppEncryptionAndHidePolicy(admin, policy);` |

**int getAppEncryptionAndHidePolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppEncryptionAndHidePolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取应用加密和应用迁移隐藏管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getAppRunningManager().setAppEncryptionAndHidePolicy(admin);` |

#### 2.5.13 获取应用运行时长

> 需要权限：应用包状态管理

**List<String[]> getAppRunInfo(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String[]> getAppRunInfo(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取所有应用运行时长 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String[]>：所有正在运行的应用累计运行情况<br>string[0]：终端应用PID，如当前未运行则为空字符串；<br>string[1]：终端应用UID；<br>string[2]：终端应用包名；<br>string[3]：终端应用已运行时间（毫秒） |
| 使用示例 | `List<String[]> appRunInfo = VivoEnterpriseFactory.getAppRunningManager().getAppRunInfo(admin);` |

#### 2.5.14 获取应用耗电

> 需要权限：应用包状态管理

**List<String[]> getAppPowerUsage(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String[]> getAppPowerUsage(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取所有应用耗电 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String[]> 终端从上次充满电到当前时刻所有应用的耗电情况<br>string[0]：终端应用包名；<br>string[1]：该终端应用的耗电量（mAh） |
| 使用示例 | `List<String[]> appPowerInfo = VivoEnterpriseFactory.getAppRunningManager().getAppPowerUsage(admin);` |

### 2.6 应用包管理类（DevicePackageManager）

#### 2.6.1 静默安装/卸载

> 需要权限：应用包状态管理

**boolean installPackage(ComponentName admin, String packagePath)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean installPackage(ComponentName admin, String packagePath)` |
| 功能描述 | 静默安装应用，用户无需确认 |
| 参数 | admin：设备管理器组件名<br>packagePath：应用包路径（带完整包名字），例： `String packagePath = "/storage/emulated/0/Android/data/" +` `"com.example.package/cache/example.apk";` |
| 返回值 | true/false 执行成功/失败（注：因为应用安装是长耗时操作，无法同步返回安装结果，<br>这里只返回安装命令执行结果，最终安装结果请通过其他方式自行获取） |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().installPackage(admin, path);` |

**boolean uninstallPackage(ComponentName admin, String packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean uninstallPackage(ComponentName admin, String packageName)` |
| 功能描述 | 静默卸载应用，用户无需确认 |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";` |
| 返回值 | true/false 卸载成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().uninstallPackage(admin,packageName);` |

**boolean uninstallPackageWithFlag(ComponentName admin, String packageName,int flag)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean uninstallPackageWithFlag(ComponentName admin, String packageName,int flag)` |
| 功能描述 | 静默卸载应用，用户无需确认，且可指定flag |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";`<br>flag：详见Android 源码PackageManager.java 文件各个flag 含义（DeleteFlags） 常用flag： 1：保留应用数据 |
| 返回值 | true/false 卸载成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().uninstallPackage(admin,packageName, flag);` |

#### 2.6.2 允许/禁止安装应用

> 需要权限：应用包状态管理

**boolean setInstallPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setInstallPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用安装管控策略，包含通过adb 安装 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止安装<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setInstallPolicy(admin, policy);` |

**int getInstallPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getInstallPolicy(ComponentName admin)` |
| 功能描述 | 获取应用安装管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止<br>int<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getInstallPolicy(admin);` |

#### 2.6.3 应用安装黑白名单策略

> 需要权限：应用包状态管理

**boolean setInstallBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setInstallBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用安装黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单列表中<br>的应用不可安装，白名单模式下，白名单列表之外的应用不可安装 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setInstallBlackWhitePolicy(admin,policy);` |

**int getInstallBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getInstallBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取应用安装黑白名单模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getInstallBlackWhitePolicy(admin);` |

#### 2.6.4 应用安装黑白名单列表

> 需要权限：应用包状态管理

**boolean addInstallBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addInstallBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用安装黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单列表中<br>的应用不可安装 |
| 参数 | admin：设备管理器组件名<br>pkgs：黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().addInstallBlackList(admin, pkgs);` |

**List<String> getInstallBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getInstallBlackList(ComponentName admin)` |
| 功能描述 | 获取应用安装黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list= VivoEnterpriseFactory.getPackageManager().getInstallBlackList(admin);` |

**boolean deleteInstallBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteInstallBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用安装黑名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().deleteInstallBlackList(admin, pkgs);` |

**boolean clearInstallBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearInstallBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用安装黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().clearInstallBlackList(admin);` |

**boolean addInstallWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addInstallWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用安装白名单列表，需配合黑白名单策略使用。白名单模式下，白名单列表之<br>外的应用不可安装 |
| 参数 | admin：设备管理器组件名<br>pkgs：白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().addInstallWhiteList(admin, pkgs);` |

**List<String> getInstallWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getInstallWhiteList(ComponentName admin)` |
| 功能描述 | 获取应用安装白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list= VivoEnterpriseFactory.getPackageManager().getInstallWhiteList(admin);` |

**boolean deleteInstallWhiteList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteInstallWhiteList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用安装白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().deleteInstallWhiteList(admin, pkgs);` |

**boolean clearInstallWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearInstallWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用安装白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().clearInstallWhiteList(admin);` |

#### 2.6.5 允许/禁止卸载应用

> 需要权限：应用包状态管理

**boolean setUninstallPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUninstallPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用卸载管控策略，包含通过adb 卸载 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止卸载<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setUninstallPolicy(admin, policy);` |

**int getUninstallPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUninstallPolicy(ComponentName admin)` |
| 功能描述 | 获取应用卸载管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getUninstallPolicy(admin);` |

#### 2.6.6 应用卸载黑名单策略

> 需要权限：应用包状态管理

**boolean setUninstallBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUninstallBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用卸载黑名单模式，配合黑名单列表使用。黑名单模式下，黑名单列表中的应<br>用不可卸载<br>注：卸载无白名单 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setUninstallBlackWhitePolicy(admin, policy);` |

**int getUninstallBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUninstallBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取应用卸载黑名单模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getUninstallBlackWhitePolicy(admin);` |

#### 2.6.7 应用卸载黑名单列表

> 需要权限：应用包状态管理

**boolean addUninstallBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addUninstallBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 添加应用卸载黑名单列表，需配合黑名单策略使用。黑名单模式下，黑名单列表中的<br>应用不可卸载 |
| 参数 | admin：设备管理器组件名<br>pkgs：黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().addUninstallBlackList(admin,pkgs);` |

**List<String> getUninstallBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getUninstallBlackList(ComponentName admin)` |
| 功能描述 | 获取应用卸载黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单应用包名列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getPackageManager().getUninstallBlackList(admin);` |

**boolean deleteUninstallBlackList(ComponentName admin, List<String> pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteUninstallBlackList(ComponentName admin, List<String> pkgs)` |
| 功能描述 | 删除应用卸载黑名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除的黑名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().deleteUninstallBlackList(admin,pkgs);` |

**boolean clearUninstallBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearUninstallBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空应用卸载黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().clearUninstallBlackList(admin,pkgs);` |

#### 2.6.8 允许/禁止安装未知来源应用

> 需要权限：应用包状态管理

**boolean setInstallUnknownSourcePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setInstallUnknownSourcePolicy(ComponentName admin, int policy)` |
| 功能描述 | 安装未知来源应用权限策略，配置后第三方应用市场每次安装应用时会弹框让用户手<br>动确认，无法直接安装其他应用，且设置里安装未知应用权限开关无法手动开启 |
| 参数 | admin：设备管理器组件名<br>policy：默认/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setInstallUnknownSourcePolicy(admin, policy);` |

**int getInstallUnknownSourcePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getInstallUnknownSourcePolicy(ComponentName admin)` |
| 功能描述 | 获取安装未知来源应用权限策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getPackageManager().setInstallUnknownSourcePolicy(admin);` |

#### 2.6.9 开启/关闭可信应用市场

> 需要权限：应用包状态管理

**boolean setInstallTrustedSourcePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setInstallTrustedSourcePolicy(ComponentName admin, int policy)` |
| 功能描述 | 开启或关闭可信应用市场，可配合可信应用市场列表使用，开启后只有可信应用市场<br>列表中的应用才可安装其他应用，默认值为关闭 |
| 参数 | admin：设备管理器组件名<br>policy：关闭/开启（0 表示关闭，1 表示开启） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setInstallTrustedSourcePolicy(admin, policy);` |

**int getInstallTrustedSourcePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getInstallTrustedSourcePolicy(ComponentName admin)` |
| 功能描述 | 获取可信应用市场策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/开启（0 表示关闭，1 表示开启） |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getInstallTrustedSourcePolicy(admin);` |

#### 2.6.10 添加/删除可信应用市场

> 需要权限：应用包状态管理

**boolean addInstallTrustedSourcePackages(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addInstallTrustedSourcePackages(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 添加可信应用市场，需配合可信应用市场策略使用，策略开启后只有可信应用市场列<br>表中的应用才可安装其他应用（注：如包名列表中添加“adb”，表示允许adb 安装） |
| 参数 | admin：设备管理器组件名<br>pkgs：可信应用市场包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().addInstallTrustedSourcePackages(admin, pkgs);` |

**List<String> getInstallTrustedSourcePackages(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getInstallTrustedSourcePackages(ComponentName admin)` |
| 功能描述 | 获取可信应用市场列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 可信应用市场包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getPackageManager().getInstallTrustedSourcePackages(admin);` |

**boolean deleteInstallTrustedSourcePackages(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteInstallTrustedSourcePackages(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除可信应用市场列表 |
| 参数 | admin：设备管理器组件名pkgs 需删除的包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().deleteInstallTrustedSourcePackages(admin, pkgs);` |

**boolean clearInstallTrustedSourcePackages(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearInstallTrustedSourcePackages(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空可信应用市场列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().clearInstallTrustedSourcePackages(admin);` |

#### 2.6.11 清除应用数据

> 需要权限：应用包状态管理

**void clearAppData(ComponentName admin, String packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void clearAppData(ComponentName admin, String packageName)` |
| 功能描述 | 直接清除应用数据，同设置里功能一致 |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";` |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getPackageManager().clearAppData(admin, packageName);` |

#### 2.6.12 添加/删除禁止清除数据应用

> 需要权限：应用包状态管理

**boolean addDisabllowedClearDataApps(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addDisabllowedClearDataApps(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 添加禁止清除数据的应用，其他任何路径均无法清除应用数据 |
| 参数 | admin：设备管理器组件名<br>pkgs：包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().addDisabllowedClearDataApps(admin, pkgs);` |

**List<String> getDisabllowedClearDataApps(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getDisabllowedClearDataApps(ComponentName admin)` |
| 功能描述 | 获取禁止清除数据的应用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 禁止清除数据包名列表，不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getPackageManager().getDisabllowedClearDataApps(admin);` |

**boolean deleteDisabllowedClearDataApps(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteDisabllowedClearDataApps(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除禁止清除数据的应用 |
| 参数 | admin：设备管理器组件名pkgs 需删除包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().deleteDisabllowedClearDataApps(admin, pkgs);` |

**boolean clearDisabllowedClearDataApps(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearDisabllowedClearDataApps(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空禁止清除数据的应用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().clearDisabllowedClearDataApps(admin);` |

#### 2.6.13 允许/禁止应用操作

> 需要权限：应用包状态管理

**boolean setAppControlPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppControlPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置应用操作管控策略，禁止后无法进行下列操作：卸载应用，清除应用缓存，清除<br>应用数据，强制停止应用，清除默认应用 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止 允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPackageManager().setAppControlPolicy(admin, policy);` |

**int getAppControlPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppControlPolicy(ComponentName admin)` |
| 功能描述 | 获取应用操作管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPackageManager().getAppControlPolicy(admin);` |

### 2.7 默认应用管理类（DeviceApplicationManager）

#### 2.7.1 默认短信应用

> 需要权限：应用程序管理

**boolean setDefaultSmsApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDefaultSmsApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)` |
| 功能描述 | 设置默认短信应用 |
| 参数 | admin：设备管理器组件名<br>componentName：默认短信应用组件名disableModify 是否允许被手动修改，true 为不允许，false 为允许 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApplicationManager().setDefaultSmsApp(admin,componentName, disableModify);` |

**ComponentName getDefaultSmsApp(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDefaultSmsApp(ComponentName admin)` |
| 功能描述 | 获取默认短信应用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | ComponentName 默认短信应用组件名，未设置返回null |
| 使用示例 | `Component componentName = VivoEnterpriseFactory.getApplicationManager().getDefaultSmsApp(admin);` |

#### 2.7.2 默认桌面

> 需要权限：应用程序管理

**boolean setDefaultLauncherApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDefaultLauncherApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)` |
| 功能描述 | 设置默认桌面（设置默认桌面的同时请禁用儿童模式，否则可能导致桌面异常） |
| 参数 | admin：设备管理器组件名<br>componentName：默认桌面应用组件名disableModify 是否允许被手动修改，true 为不允许，false 为允许 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApplicationManager().setDefaultLauncherApp(admin,componentName, disableModify);` |

**ComponentName getDefaultLauncherApp(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDefaultLauncherApp(ComponentName admin)` |
| 功能描述 | 获取默认桌面 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | ComponentName 默认桌面应用组件名，未设置返回null |
| 使用示例 | `Component componentName = VivoEnterpriseFactory.getApplicationManager().getDefaultLauncherApp(admin);` |

#### 2.7.3 默认浏览器

> 需要权限：应用程序管理

**boolean setDefaultBrowserApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDefaultBrowserApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)` |
| 功能描述 | 设置默认浏览器 |
| 参数 | admin：设备管理器组件名<br>componentName：默认浏览器应用组件名disableModify 是否允许被手动修改，true 为不允许，false 为允许 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApplicationManager().setDefaultBrowserApp(admin,componentName, disableModify);` |

**ComponentName getDefaultBrowserApp(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDefaultBrowserApp(ComponentName admin)` |
| 功能描述 | 获取默认浏览器 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | ComponentName 默认浏览器应用组件名，未设置返回null |
| 使用示例 | `Component componentName = VivoEnterpriseFactory.getApplicationManager().getDefaultBrowserApp(admin);` |

#### 2.7.4 默认邮件应用

> 需要权限：应用程序管理

**boolean setDefaultEmailApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDefaultEmailApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)` |
| 功能描述 | 设置默认邮件应用 |
| 参数 | admin：设备管理器组件名<br>componentName：默认邮件应用组件名disableModify 是否允许被手动修改，true 为不允许，false 为允许 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApplicationManager().setDefaultEmailApp(admin,componentName, disableModify);` |

**ComponentName getDefaultEmailApp(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDefaultEmailApp(ComponentName admin)` |
| 功能描述 | 获取默认邮件应用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | ComponentName 默认邮件应用组件名，未设置返回null |
| 使用示例 | `Component componentName = VivoEnterpriseFactory.getApplicationManager().getDefaultEmailApp(admin);` |

#### 2.7.5 默认输入法

> 需要权限：应用程序管理

**boolean setDefaultInputMethodApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDefaultInputMethodApp(ComponentName admin, ComponentNamecomponentName, boolean disableModify)` |
| 功能描述 | 设置默认输入法 |
| 参数 | admin：设备管理器组件名<br>componentName：默认输入法应用组件名disableModify 是否允许被手动修改，true 为不允许，false 为允许 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApplicationManager().setDefaultInputMethodApp(admin,componentName, disableModify);` |

**ComponentName getDefaultInputMethodApp(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ComponentName getDefaultInputMethodApp(ComponentName admin)` |
| 功能描述 | 获取默认输入法 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | ComponentName 默认输入法应用组件名，未设置返回null |
| 使用示例 | `Component componentName = VivoEnterpriseFactory.getApplicationManager().getDefaultInputMethodApp(admin);` |

### 2.8 APN 管理类（DeviceApnManager）

#### 2.8.1 允许/禁止修改APN

> 需要权限：APN 管理

**boolean setApnPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setApnPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止修改APN，禁止后用户无法手动修改APN 配置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止 允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().setApnPolicy(admin, policy);` |

**int getApnPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getApnPolicy(ComponentName admin)` |
| 功能描述 | 获取允许/禁止修改APN 策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getApnManager().getApnPolicy(admin);` |

#### 2.8.2 启用/禁用代理APN

> 需要权限：APN 管理

**void setOverrideApnsEnabled(ComponentName admin, boolean enabled)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setOverrideApnsEnabled(ComponentName admin, boolean enabled)` |
| 功能描述 | 启用/禁用代理APN，默认为禁用状态，启用后，SIM 卡原来的默认APN 即刻失效，<br>启用代理APN 配置取代原始APN，代理APN 只存在于后台，用户无感知（在设置里<br>的APN 菜单界面不会看到任何改变，开启后，如代理APN 未正确添加，设备将无法<br>联网） |
| 参数 | admin：设备管理器组件名<br>enabled：true/false 启用/禁用 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getApnManager().setOverrideApnsEnabled(admin, enabled);` |

**boolean isOverrideApnEnabled(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean isOverrideApnEnabled(ComponentName admin)` |
| 功能描述 | 获取代理APN 启用/禁用策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 启用/禁用 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().isOverrideApnEnabled(admin);` |

#### 2.8.3 添加/删除代理APN

> 需要权限：APN 管理

**int addOverrideApn(ComponentName admin, ApnSetting apnSetting)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int addOverrideApn(ComponentName admin, ApnSetting apnSetting)` |
| 功能描述 | 添加代理APN，添加的APN 用户无感知，不会显示在APN 界面，只能通过接口获取，<br>不可重复添加相同APN |
| 参数 | admin：设备管理器组件名<br>apnSetting：apn 配置 |
| 返回值 | int 添加成功返回apn 的id，失败返回-1 |
| 使用示例 | `int id = VivoEnterpriseFactory.getApnManager().addOverrideApn(admin, apnSetting);` |

**boolean updateOverrideApn(ComponentName admin, int apnId, ApnSetting`<br>apnSetting)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean updateOverrideApn(ComponentName admin, int apnId, ApnSetting`<br>apnSetting) |
| 功能描述 | 更新已添加的代理APN 配置 |
| 参数 | admin：设备管理器组件名<br>apnId：已添加apn 的id<br>apnSetting：apn 配置 |
| 返回值 | true/false 更新成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().updateOverrideApn(admin, apnId, apn);` |

**boolean removeOverrideApn(ComponentName admin, int apnId)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean removeOverrideApn(ComponentName admin, int apnId)` |
| 功能描述 | 删除已添加的代理APN |
| 参数 | admin：设备管理器组件名<br>apnId：已添加apn 的id |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().removeOverrideApn(admin, apnId);` |

**List<ApnSetting> getOverrideApns(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<ApnSetting> getOverrideApns(ComponentName admin)` |
| 功能描述 | 获取已添加的代理APN 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<ApnSetting> 代理apn 配置列表 |
| 使用示例 | `List<ApnSetting> list = VivoEnterpriseFactory.getApnManager().getOverrideApns(admin);` |

#### 2.8.4 添加/删除屏蔽recovery 机制apn 列表

> 需要权限：APN 管理

**boolean addApnDisableRecoveryList(ComponentName admin, List<String>`<br>apnNames)<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addApnDisableRecoveryList(ComponentName admin, List<String>`<br>apnNames)<br>(Android12 及以上支持) |
| 功能描述 | 添加屏蔽recovery 机制的apn |
| 参数 | admin：设备管理器组件名<br>apnNames：apn 名称列表 |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().addApnDisableRecoveryList(admin,apnNames);` |

**List<String> getApnDisableRecoveryList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getApnDisableRecoveryList(ComponentName admin)` |
| 功能描述 | 获取已添加的屏蔽recovery 机制的apn 名称 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> apn 名称列表 |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getApnManager().getApnDisableRecoveryList(admin);` |

**boolean deleteApnDisableRecoveryList(ComponentName admin, List<String>`<br>apnNames)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteApnDisableRecoveryList(ComponentName admin, List<String>`<br>apnNames) |
| 功能描述 | 删除屏蔽recovery 机制的apn |
| 参数 | admin：设备管理器组件名<br>apnNames：apn 名称列表 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().deleteApnDisableRecoveryList(admin,apnNames);` |

#### 2.8.5 添加/删除APN

> 需要权限：APN 管理

**int addApn(ComponentName admin, ApnSetting apnSetting)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int addApn(ComponentName admin, ApnSetting apnSetting)`<br>(Android12 及以上支持) |
| 功能描述 | 添加APN，完成后将显示在APN 设置界面，注意只能添加与当前SIM 卡匹配的APN，<br>否则无法显示 |
| 参数 | admin：设备管理器组件名<br>apnSetting：apn 配置 |
| 返回值 | int 添加成功返回apn 的id，失败返回-1 |
| 使用示例 | `int id = VivoEnterpriseFactory.getApnManager().addApn(admin, apnSettings);` |

**List<Integer> getApnList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<Integer> getApnList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取当前SIM 卡可用APN ID |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `List<Integer>`<br>apn id 列表（无SIM 卡返回null） |
| 使用示例 | `List<Integer> list = VivoEnterpriseFactory.getApnManager().getApnList(admin);` |

**boolean deleteApn(ComponentName admin, int apnId)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteApn(ComponentName admin, int apnId)`<br>(Android12 及以上支持) |
| 功能描述 | 删除已添加的APN |
| 参数 | admin：设备管理器组件名<br>apnId：已添加apn 的id |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().deleteApn(admin, apnId);` |

#### 2.8.6 获取APN 详情

> 需要权限：APN 管理

**ApnSetting getApnInfo(ComponentName admin, int apnId)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `ApnSetting getApnInfo(ComponentName admin, int apnId)`<br>(Android12 及以上支持) |
| 功能描述 | 获取apn 详细参数 |
| 参数 | admin：设备管理器组件名<br>apnId：已存在apn 的id |
| 返回值 | ApnSetting apn 详细参数 |
| 使用示例 | `ApnSetting apnInfo = VivoEnterpriseFactory.getApnManager().getApnInfo(admin, apnId);` |

#### 2.8.7 切换APN

> 需要权限：APN 管理

**boolean setCurrentApn(ComponentName admin, int apnId)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setCurrentApn(ComponentName admin, int apnId)`<br>(Android12 及以上支持) |
| 功能描述 | 切换当前使用APN，该APN 必须与当前默认SIM 卡匹配 |
| 参数 | admin：设备管理器组件名<br>apnId：当前SIM 卡可用的apn id |
| 返回值 | true/false 切换成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().setCurrentApn(admin, apnId);` |

**int getCurrentApn(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getCurrentApn(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取当前正在使用的APN ID |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>当前正在使用的apn id（无SIM 卡返回-1） |
| 使用示例 | `int id = VivoEnterpriseFactory.getApnManager().getCurrentApn(admin);` |

#### 2.8.8 恢复系统默认APN 配置

> 需要权限：APN 管理

**boolean resetApnNetworkSetting(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean resetApnNetworkSetting(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 恢复系统默认APN 配置，所有添加的APN 全部清除 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 恢复成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getApnManager().resetApnNetworkSetting(admin);` |

### 2.9 VPN 管理类（DeviceVpnManager）

77

注：操作某些VPN 接口可能需要额外申请android.permission.CONTROL_VPN 等权限

#### 2.9.1 允许/禁止修改VPN

> 需要权限：VPN 管理

**boolean setVpnPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setVpnPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止修改VPN，禁止后用户无法修改VPN 配置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getVpnManager().setVpnPolicy(admin, policy);` |

**int getVpnPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getVpnPolicy(ComponentName admin)` |
| 功能描述 | 获取允许/禁止修改VPN 策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getVpnManager().getVpnPolicy(admin);` |

#### 2.9.2 锁定/取消始终连接的VPN 应用

> 需要权限：VPN 管理

**boolean setAlwaysOnVpnPackage(ComponentName admin, String vpnPackage,boolean lockdown)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAlwaysOnVpnPackage(ComponentName admin, String vpnPackage,boolean lockdown)` |
| 功能描述 | 锁定始终连接的VPN 应用，锁定一个VPN 应用为始终连接状态，即设备所有网络只<br>能通过该VPN 应用连接，直至取消。<br>注：如该VPN 应用无法连接，会导致设备一直无法联网直到调用接口取消锁定 |
| 参数 | admin：设备管理器组件名<br>vpnPackage：VPN 应用包名<br>lockdown：true/false 锁定始终连接/取消锁定 |
| 返回值 | true/false 设置成功/失败<br>注：如该VPN 应用不支持始终连接方式，会抛出UnsupportedOperationException |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getVpnManager().setAlwaysOnVpnPackage(admin,vpnPackage, lockdown);` |

**String getAlwaysOnVpnPackage(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getAlwaysOnVpnPackage(ComponentName admin)` |
| 功能描述 | 获取始终连接的VPN 应用 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `String`<br>当前始终连接的VPN 应用包名，不存在时返回null |
| 使用示例 | `String vpnPackage = VivoEnterpriseFactory.getVpnManager().getAlwaysOnVpnPackage(admin);` |

#### 2.9.3 添加/移除VPN

> 需要权限：VPN 管理

**boolean addVpnProfile(ComponentName admin, CustVpnProfile profile, booleanconnect, boolean lockdown)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addVpnProfile(ComponentName admin, CustVpnProfile profile, booleanconnect, boolean lockdown)` |
| 功能描述 | 添加VPN |
| 参数 | admin：设备管理器组件名<br>profile：VPN 配置<br>connect：是否立即连接<br>lockdown：是否锁定始终连接 注：锁定始终连接代表设备所有网络只能通过该VPN 连接，如该VPN 无法连接，将 导致设备一直无法联网直至调用接口删除VPN |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getVpnManager().addVpnProfile(admin, profile, connect,lockdown);` |

**List<CustVpnProfile> getVpnProfiles(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<CustVpnProfile> getVpnProfiles(ComponentName admin)` |
| 功能描述 | 获取当前VPN 列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<CustVpnProfile> VPN 配置列表，不存在时返回null |
| 使用示例 | `List<CustVpnProfile> list = VivoEnterpriseFactory.getVpnManager().getVpnProfiles(admin);` |

**boolean deleteVpnProfile(ComponentName admin, String vpnKey)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteVpnProfile(ComponentName admin, String vpnKey)` |
| 功能描述 | 删除VPN |
| 参数 | admin：设备管理器组件名<br>vpnKey：VPN 配置中的key 字段值 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getVpnManager().deleteVpnProfile(admin, vpnKey);` |

### 2.10 网络管理类（DeviceNetworkManager）

#### 2.10.1 允许/禁止数据漫游

> 需要权限：网络状态管理

**boolean setDataRoamingPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDataRoamingPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止数据漫游，禁止后用户无法修改漫游设置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setDataRoamingPolicy(admin,policy);` |

**int getDataRoamingPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDataRoamingPolicy(ComponentName admin)` |
| 功能描述 | 获取数据漫游策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getDataRoamingPolicy(admin);` |

#### 2.10.2 允许/禁止网络共享

> 需要权限：网络状态管理

**boolean setTetheringPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setTetheringPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止网络共享（包含各类热点） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setTetheringPolicy(admin, policy);` |

**int getTetheringPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getTetheringPolicy(ComponentName admin)` |
| 功能描述 | 获取网络共享策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getTetheringPolicy(admin);` |

#### 2.10.3 允许/禁止移动网络配置

> 需要权限：网络状态管理

**boolean setConfigNetworkPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setConfigNetworkPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止修改移动网络配置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setConfigNetworkPolicy(admin,policy);` |

**int getConfigNetworkPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getConfigNetworkPolicy(ComponentName admin)` |
| 功能描述 | 获取移动网络配置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getConfigNetworkPolicy(admin);` |

#### 2.10.4 允许/禁止/强开移动数据网络

> 需要权限：网络状态管理

**boolean setDataNetworkPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDataNetworkPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止/强制打开移动网络数据 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制打开<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setDataNetworkPolicy(admin,policy);` |

**int getDataNetworkPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDataNetworkPolicy(ComponentName admin)` |
| 功能描述 | 获取移动网络数据策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制打开<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getDataNetworkPolicy(admin);` |

#### 2.10.5 域名访问黑白名单策略

83

> 需要权限：网络地址管理

**boolean setDomainBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDomainBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置域名访问黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单列表中<br>的域名不可访问，白名单模式下，白名单列表之外的域名不可访问（注：对vivo 浏览<br>器生效，其他应用可部分生效，如果应用有自己的服务器代理、dns 缓存，域名黑白<br>名单无法管控） |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setDomainBlackWhitePolicy(admin,policy);` |

**int getDomainBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDomainBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取域名访问黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getDomainBlackWhitePolicy(admin);` |

#### 2.10.6 域名访问黑白名单列表

> 需要权限：网络地址管理

**boolean addDomainBlackList(ComponentName admin, List<String> urls)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addDomainBlackList(ComponentName admin, List<String> urls)` |
| 功能描述 | 添加域名访问黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单列表中<br>的域名不可访问 |
| 参数 | admin：设备管理器组件名<br>urls：黑名单域名关键字列表 注：添加域名黑白名单时，添加的必须是域名关键字，如：要添加"baidu",而不是添加 "www.baidu.com"，否则可能通过其他跳转方式访问，例： `List<String> urls = new ArrayList<>();` `urls.add("baidu");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().addDomainBlackList(admin, urls);` |

**List<String> getDomainBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getDomainBlackList(ComponentName admin)` |
| 功能描述 | 获取域名黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单域名关键字列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getNetworkManager().getDomainBlackList(admin);` |

**boolean deleteDomainBlackList(ComponentName admin, List<String> urls)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteDomainBlackList(ComponentName admin, List<String> urls)` |
| 功能描述 | 删除域名黑名单列表 |
| 参数 | admin：设备管理器组件名<br>urls：需删除的域名关键字列表，例： `List<String> urls = new ArrayList<>();` `urls.add("baidu");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().deleteDomainBlackList(admin, urls);` |

**boolean clearDomainBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearDomainBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空域名黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().clearDomainBlackList(admin);` |

**boolean addDomainWhiteList(ComponentName admin, List<String> urls)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addDomainWhiteList(ComponentName admin, List<String> urls)` |
| 功能描述 | 添加域名访问白名单列表，需配合黑白名单策略使用。白名单模式下，白名单列表之<br>外的域名不可访问 |
| 参数 | admin：设备管理器组件名<br>urls：白名单域名关键字列表 注：添加域名黑白名单时，添加的必须是域名关键字，如：要添加"baidu",而不是添加 "www.baidu.com"，例： `List<String> urls = new ArrayList<>();` `urls.add("baidu");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().addDomainWhiteList(admin, urls);` |

**List<String> getDomainWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getDomainWhiteList(ComponentName admin)` |
| 功能描述 | 获取域名白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单域名关键字列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getNetworkManager().getDomainWhiteList(admin);` |

**boolean deleteDomainWhiteList(ComponentName admin, List<String> urls)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteDomainWhiteList(ComponentName admin, List<String> urls)` |
| 功能描述 | 删除域名白名单列表 |
| 参数 | admin：设备管理器组件名<br>urls：需删除的域名关键字列表，例： `List<String> urls = new ArrayList<>();` `urls.add("baidu");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().deleteDomainWhiteList(admin,urls);` |

**boolean clearDomainWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearDomainWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空域名白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().clearDomainWhiteList(admin);` |

#### 2.10.7 IP 地址访问黑白名单策略

> 需要权限：网络地址管理

**boolean setIpAddrBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setIpAddrBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置IP 地址访问黑名单模式，配合黑名单列表使用。黑名单模式下，黑名单列表中的<br>IP 地址不可访问，白名单模式下，白名单列表之外的IP 地址不可访问 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setIpAddrBlackWhitePolicy(admin,policy);` |

**int getIpAddrBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getIpAddrBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取IP 地址访问黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getIpAddrBlackWhitePolicy(admin);` |

#### 2.10.8 IP 地址访问黑白名单列表

> 需要权限：网络地址管理

**boolean addIpAddrBlackList (ComponentName admin, List<String> ips)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addIpAddrBlackList (ComponentName admin, List<String> ips)` |
| 功能描述 | 添加IP 地址访问黑名单列表，需配合黑名单策略使用。黑名单模式下，黑名单列表中<br>的IP 地址不可访问 |
| 参数 | admin：设备管理器组件名<br>ips：黑名单IP 地址列表，例： `List<String> ips= new ArrayList<>();` `ips.add("255.255.255.255");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().addIpAddrBlackList(admin, ips);` |

**List<String> getIpAddrBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getIpAddrBlackList(ComponentName admin)` |
| 功能描述 | 获取IP 地址黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单IP 地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getNetworkManager().getIpAddrBlackList(admin);` |

**boolean deleteIpAddrBlackList(ComponentName admin, List<String> ips)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteIpAddrBlackList(ComponentName admin, List<String> ips)` |
| 功能描述 | 删除IP 地址黑名单列表 |
| 参数 | admin：设备管理器组件名<br>ips：需删除的IP 地址列表，例： `List<String> ips= new ArrayList<>();` `ips.add("255.255.255.255");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().deleteIpAddrBlackList(admin, ips);` |

**boolean clearIpAddrBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearIpAddrBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空IP 地址黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().clearIpAddrBlackList(admin);` |

**boolean addIpAddrWhiteList (ComponentName admin, List<String> ips)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addIpAddrWhiteList (ComponentName admin, List<String> ips)` |
| 功能描述 | 添加IP 地址访问白名单列表，需配合白名单策略使用。白名单模式下，白名单列表之<br>外的IP 地址不可访问 |
| 参数 | admin：设备管理器组件名<br>ips：白名单IP 地址列表，例： `List<String> ips= new ArrayList<>();` `ips.add("255.255.255.255");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().clearIpAddrBlackList(admin, ips);` |

**List<String> getIpAddrWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getIpAddrWhiteList(ComponentName admin)` |
| 功能描述 | 获取IP 地址白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单IP 地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getNetworkManager().getIpAddrWhiteList(admin);` |

**boolean deleteIpAddrWhiteList(ComponentName admin, List<String> ips)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteIpAddrWhiteList(ComponentName admin, List<String> ips)` |
| 功能描述 | 删除IP 地址白名单列表 |
| 参数 | admin：设备管理器组件名<br>ips：需删除的IP 地址列表，例： `List<String> ips= new ArrayList<>();` `ips.add("255.255.255.255");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().deleteIpAddrWhiteList(admin, ips);` |

**boolean clearIpAddrWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearIpAddrWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空IP 地址白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().clearIpAddrWhiteList(admin);` |

#### 2.10.9 获取应用消耗流量

> 需要权限：网络状态管理

**long getAppTrafficBytes(ComponentName admin, int mode, String packageName,int direct)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `long getAppTrafficBytes(ComponentName admin, int mode, String packageName,int direct)` |
| 功能描述 | 获取应用消耗的流量，可区分流量种类和上下行 |
| 参数 | admin：设备管理器组件名<br>mode：流量种类：0 全部流量 1 数据网络流量 2 WLAN 网络流量<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";`<br>direct：上下行：0 全部流量 1 下行流量 2 上行流量 |
| 返回值 | long 应用消耗的流量值（单位byte） |
| 使用示例 | `long bytes = VivoEnterpriseFactory.getNetworkManager().getAppTrafficBytes(admin, mode,`<br>packageName, direct) |

#### 2.10.10 数据网络卡槽限制

> 需要权限：网络状态管理

**boolean setDataNetworkSlotPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDataNetworkSlotPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置数据网络卡槽管控策略 |
| 参数 | admin：设备管理器组件名<br>policy：默认/仅允许卡槽1 使用数据网络/仅允许卡槽2 使 用数据网络<br>Policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 仅允许卡槽1 使用数据网络：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 仅允许卡槽2 使用数据网络：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getNetworkManager().setDataNetworkSlotPolicy(admin,policy);` |

**int getDataNetworkSlotPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDataNetworkSlotPolicy(ComponentName admin)` |
| 功能描述 | 获取数据网络卡槽管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/仅允许卡槽1 使用数据网络/仅允许卡槽2 使用数据网络<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>仅允许卡槽1 使用数据网络：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>仅允许卡槽2 使用数据网络：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getNetworkManager().getDataNetworkSlotPolicy(admin);` |

### 2.11 按键管理类（DeviceKeyEventManager）

#### 2.11.1 允许/禁用HOME 键

> 需要权限：按键事件管理

**boolean setHomeKeyPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setHomeKeyPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用HOME 键 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setHomeKeyPolicy(admin, policy);` |

**int getHomeKeyPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getHomeKeyPolicy(ComponentName admin)` |
| 功能描述 | 获取HOME 键策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getHomeKeyPolicy(admin);` |

#### 2.11.2 允许/禁用BACK 键

> 需要权限：按键事件管理

**boolean setBackKeyPolicy (ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBackKeyPolicy (ComponentName admin, int policy)` |
| 功能描述 | 设置允许禁用BACK 键 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setBackKeyPolicy(admin, policy);` |

**int getBackKeyPolicy (ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBackKeyPolicy (ComponentName admin)` |
| 功能描述 | 获取BACK 键策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getBackKeyPolicy(admin);` |

#### 2.11.3 允许/禁用MENU 键

> 需要权限：按键事件管理

**boolean setMenuKeyPolicy (ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMenuKeyPolicy (ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用MENU 键，包括最近任务键和上滑快捷面板 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setMenuKey(admin, policy);` |

**int getMenuKeyPolicy (ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMenuKeyPolicy (ComponentName admin)` |
| 功能描述 | 获取MENU 键策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getMenuKey(admin);` |

#### 2.11.4 允许/禁用状态栏

> 需要权限：按键事件管理

94

**boolean setStatusBarPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setStatusBarPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用下拉状态栏（注意此时通知也无法通过状态栏查看） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setStatusBarPolicy(admin, policy);` |

**int getStatusBarPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getStatusBarPolicy(ComponentName admin)` |
| 功能描述 | 获取状态栏策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getStatusBarPolicy(admin);` |

#### 2.11.5 允许/禁用关机面板

> 需要权限：关机事件管理

（注：此类功能需手机ROM 支持SDK 2.0 才可使用）

**boolean setPowerPanelPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPowerPanelPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用长按电源键的关机面板 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setPowerPanelPolicy(admin,policy);` |

**int getPowerPanelPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPowerPanelPolicy(ComponentName admin)` |
| 功能描述 | 获取关机面板策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getPowerPanelPolicy(admin);` |

#### 2.11.6 允许/禁用安全模式

> 需要权限：按键事件管理

**boolean setSafeModePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSafeModePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用安全模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setSafeModePolicy(admin, policy);` |

**int getSafeModePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getSafeModePolicy(ComponentName admin)` |
| 功能描述 | 获取安全模式策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getSafeModePolicy(admin);` |

#### 2.11.7 允许/禁用音量调节

> 需要权限：按键事件管理

**boolean setVolumePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setVolumePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用音量调节，禁用后，用户无法手动调节音量，且除通话免提外，铃声、<br>闹钟、音乐等都会静音 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setVolumePolicy(admin, policy);` |

**int getVolumePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getVolumePolicy(ComponentName admin)` |
| 功能描述 | 获取音量调节策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getVolumePolicy(admin);` |

#### 2.11.8 设置长按音量上键策略

> 需要权限：按键事件管理

**boolean setVolumeUpKeyLongPressPolicy(ComponentName admin, String`<br>packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setVolumeUpKeyLongPressPolicy(ComponentName admin, String`<br>packageName) |
| 功能描述 | 设置长按音量上键定制包名，设置成功后长按音量上键，系统会发送action（见Utils.<br>ACTION_VIVO_EMM_VOLUMEUP_LONGPRESS）给应用，应用端需实现按键定制<br>action 功能 |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，为null 则取消定制策略，例： `String packagePath = "com.example.packageName";` |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setVolumeUpKeyLongPressPolicy(admin,packageName);`<br>常用方案<br>被设定应用内提供一个服务用于关联该事件，当音量上键事件被触发，同时该应用处于前台，系统会拉起被设定应用中关联<br>了音量上键事件的服务。<br>AndroidManifest.xml<br>`<service android:name=".ExampleService" android:enabled="true" android:exported="true"> <intent-filter> <action android:name="vivo.app.action.VIVO_EMM_VOLUMEUP_LONGPRESS" /> </intent-filter> </service>`<br>ExampleService.java<br>@Override<br>`public int onStartCommand(Intent intent, int flags, int startId) { if (intent != null) { String action = intent.getAction(); int down = intent.getIntExtra("action", 0); if(down == 0){ switch (action) {`<br>case Utils.ACTION_VIVO_EMM_VOLUMEUP_LONGPRESS:<br>`//to do break; } } } return super.onStartCommand(intent, flags, startId); 15. }` |

**String getVolumeUpKeyLongPressPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getVolumeUpKeyLongPressPolicy(ComponentName admin)` |
| 功能描述 | 获取长按音量上键定制包名 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | string 应用包名 |
| 使用示例 | `String packageName = VivoEnterpriseFactory.getKeyEventManager().getVolumeUpKeyLongPressPolicy(admin);` |

#### 2.11.9 设置长按AI 键策略

> 需要权限：按键事件管理

**boolean setAIKeyLongPressPolicy(ComponentName admin, String packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAIKeyLongPressPolicy(ComponentName admin, String packageName)` |
| 功能描述 | 设置长按AI 键定制包名，设置成功后长按AI 键，系统会发送action（见Utils.<br>ACTION_VIVO_EMM_JOVIKEY_LONGPRESS）给应用，应用端需实现按键定制<br>action 功能 |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";` |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setAIKeyLongPressPolicy(admin,packageName);` |

**String getAIKeyLongPressPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getAIKeyLongPressPolicy(ComponentName admin)` |
| 功能描述 | 获取长按AI 键定制包名 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | string 应用包名 |
| 使用示例 | `String packageName = VivoEnterpriseFactory.getKeyEventManager().getAIKeyLongPressPolicy(admin);` |

#### 2.11.10 设置亮屏下按电源键休眠策略

> 需要权限：按键事件管理

**boolean setSleepByPowerKeyPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSleepByPowerKeyPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁用亮屏下按电源键休眠策略，禁用后，在亮屏状态下按电源键：不灭屏不<br>锁屏。但如果已经灭屏，允许唤醒 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getKeyEventManager().setVolumeUpKeyLongPressPolicy(admin, policy);` |

**int getSleepByPowerKeyPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getSleepByPowerKeyPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取亮屏下按电源键休眠策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getKeyEventManager().getVolumeUpKeyLongPressPolicy(admin);` |

### 2.12 操作管理类（DeviceOperationManager）

#### 2.12.1 关机

> 需要权限：操作行为管理

**void shutDown(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void shutDown(ComponentName admin)` |
| 功能描述 | 关机 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getOperationManager().shutDown(admin);` |

#### 2.12.2 重启

> 需要权限：操作行为管理

**void reboot(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void reboot(ComponentName admin)` |
| 功能描述 | 重启 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getOperationManager().reboot(admin);` |

#### 2.12.3 截屏

> 需要权限：截屏管理

**Bitmap captureScreen(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `Bitmap captureScreen(ComponentName admin)` |
| 功能描述 | 截屏 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | Bitmap 当前屏幕截图 |
| 使用示例 | `Bitmap screenBitmap = VivoEnterpriseFactory.getOperationManager().captureScreen(admin);` |

#### 2.12.4 允许/禁止截屏

> 需要权限：截屏管理

**void setScreenCapturePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setScreenCapturePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止截屏，禁用后不允许任何方式截屏 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getOperationManager().setScreenCapturePolicy(admin, policy);` |

**int getScreenCapturePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getScreenCapturePolicy(ComponentName admin)` |
| 功能描述 | 获取截屏策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getScreenCapturePolicy(admin);` |

#### 2.12.5 允许/禁止切换语言

> 需要权限：语言管理

**boolean setLocalePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setLocalePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止切换语言 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setLocalePolicy(admin, policy);` |

**int getLocalePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getLocalePolicy(ComponentName admin)` |
| 功能描述 | 获取切换语言策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getLocalePolicy(admin);` |

#### 2.12.6 允许/禁止配置帐户

> 需要权限：账号管理

103

**boolean setAccountModifyPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAccountModifyPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止帐户配置，不可添加修改帐户信息（注意：禁用后vivo 账号也无法登录，<br>已登录的无影响） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setAccountModifyPolicy(admin,policy);` |

**int getAccountModifyPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAccountModifyPolicy(ComponentName admin)` |
| 功能描述 | 获取帐户配置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getAccountModifyPolicy(admin);` |

#### 2.12.7 允许/禁止修改时间日期

> 需要权限：时间日期管理

**boolean setDataTimePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDataTimePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止修改时间日期 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setDataTimePolicy(admin, policy);` |

**int getDataTimePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDataTimePolicy(ComponentName admin)` |
| 功能描述 | 获取修改时间日期策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getDataTimePolicy(admin);` |

#### 2.12.8 开启/关闭强制自动对时

> 需要权限：时间日期管理

**void setAutoTimeOffPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setAutoTimeOffPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置开启/关闭强制自动获取时间日期，用户无法手动修改时间 |
| 参数 | admin：设备管理器组件名<br>policy：默认/开启（0：默认1：开启） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `VivoEnterpriseFactory.getOperationManager().setAutoTimeOffPolicy(admin, policy);` |

**int getAutoTimeOffPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAutoTimeOffPolicy(ComponentName admin)` |
| 功能描述 | 获取修改时间日期策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 默认/开启（0：默认1：开启） |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getAutoTimeOffPolicy(admin);` |

#### 2.12.9 清除手机数据

> 需要权限：备份和重置管理

**void wipeData(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void wipeData(ComponentName admin)` |
| 功能描述 | 清除手机数据，不包含外置SD 卡 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getOperationManager().wipeData(admin);` |

#### 2.12.10 格式化SD 卡

> 需要权限：备份和重置管理

**boolean formatSDCard(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean formatSDCard(ComponentName admin)` |
| 功能描述 | 格式化外置SD 卡 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 格式化成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().formatSDCard(admin);` |

#### 2.12.11 允许/禁止恢复出厂设置

> 需要权限：备份和重置管理

**boolean setFactoryResetPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setFactoryResetPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止恢复出厂设置，建议同时禁止硬件恢复出厂设置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setFactoryResetPolicy(admin,policy);` |

**int getFactoryResetPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getFactoryResetPolicy(ComponentName admin)` |
| 功能描述 | 获取恢复出厂设置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getFactoryResetPolicy(admin);` |

#### 2.12.12 允许/禁止硬件恢复出厂设置

> 需要权限：硬件重置管理

**boolean setHardFactoryResetPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setHardFactoryResetPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止Recovery 模式下恢复出厂设置（注：该接口只专门针对Recovery 模式<br>下的清除所有数据功能） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setHardFactoryResetPolicy(admin, policy);` |

**int getHardFactoryResetPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getHardFactoryResetPolicy(ComponentName admin)` |
| 功能描述 | 获取硬件恢复出厂设置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getHardFactoryResetPolicy(admin);` |

#### 2.12.13 允许/禁止小游戏

> 需要权限：操作行为管理

**boolean setFunGamePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setFunGamePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止连续点击Android 版本出现的小游戏 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setFunGamePolicy(admin, policy);` |

**int getFunGamePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getFunGamePolicy(ComponentName admin)` |
| 功能描述 | 获取小游戏策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getFunGamePolicy(admin);` |

#### 2.12.14 允许/禁止剪贴板

> 需要权限：输入管理

**boolean setClipboardPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setClipboardPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止系统剪贴板，无法复制粘贴（应用内自己实现的复制粘贴无法管控） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setClipboardPolicy(admin, policy);` |

**int getClipboardPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getClipboardPolicy(ComponentName admin)` |
| 功能描述 | 获取剪贴板策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getClipboardPolicy(admin);` |

#### 2.12.15 允许/禁止调节亮度

109

> 需要权限：显示与亮度管理

**boolean setBrightnessPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBrightnessPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止调节亮度 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setBrightnessPolicy(admin,policy);` |

**int getBrightnessPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBrightnessPolicy(ComponentName admin)` |
| 功能描述 | 获取调节亮度策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getBrightnessPolicy(admin);` |

#### 2.12.16 允许/禁止修改息屏时间

> 需要权限：显示与亮度管理

**boolean setScreenTimeoutPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setScreenTimeoutPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止修改自动锁屏时间 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setScreenTimeoutPolicy(admin,policy);` |

**int getScreenTimeoutPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getScreenTimeoutPolicy(ComponentName admin)` |
| 功能描述 | 获取自动锁屏时间策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getScreenTimeoutPolicy(admin);` |

#### 2.12.17 允许/禁止备份数据

> 需要权限：备份和重置管理

**boolean setBackupPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBackupPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止备份数据（云服务） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setBackupPolicy(admin, policy);` |

**int getBackupPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBackupPolicy(ComponentName admin)` |
| 功能描述 | 获取备份数据策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getBackupPolicy(admin);` |

#### 2.12.18 允许/禁止配置壁纸

> 需要权限：操作行为管理

**boolean setConfigWallpaperPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setConfigWallpaperPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止配置壁纸 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setConfigWallpaperPolicy(admin,policy);` |

**int getConfigWallpaperPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getConfigWallpaperPolicy(ComponentName admin)` |
| 功能描述 | 获取壁纸配置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getConfigWallpaperPolicy(admin);` |

#### 2.12.19 允许/禁止省电模式

> 需要权限：操作行为管理

**boolean setPowerSavingPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPowerSavingPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止省电、超级省电模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setPowerSavingPolicy(admin,policy);` |

**int getPowerSavingPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPowerSavingPolicy(ComponentName admin)` |
| 功能描述 | 获取省电策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getPowerSavingPolicy(admin);` |

#### 2.12.20 获取浏览器历史记录

> 需要权限：操作行为管理

**List<String> getBrowserHistory(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getBrowserHistory(ComponentName admin)` |
| 功能描述 | 获取浏览器历史记录（注：仅限获取vivo 系统浏览器记录，不支持三方浏览器） |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 网页访问记录的URL 集合 |
| 使用示例 | `List<String> browserHistory = VivoEnterpriseFactory.getOperationManager().getBrowserHistory(admin);` |

#### 2.12.21 允许/禁止模拟定位

> 需要权限：操作行为管理

**boolean setMockLocationPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMockLocationPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止模拟定位（开发者模式下），防止用户伪造位置信息 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setMockLocationPolicy(admin,policy);` |

**int getMockLocationPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMockLocationPolicy(ComponentName admin)` |
| 功能描述 | 获取模拟定位策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getMockLocationPolicy(admin);` |

#### 2.12.22 允许/禁止全局通知

114

> 需要权限：操作行为管理

**boolean setGlobalNotificationPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setGlobalNotificationPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止全局通知，禁止时，除应用权限白名单列表之外的其他所有应用通知提<br>示禁用 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setGlobalNotificationPolicy(admin,policy);` |

**int getGlobalNotificationPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getGlobalNotificationPolicy(ComponentName admin)` |
| 功能描述 | 获取全局通知管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getGlobalNotificationPolicy(admin);` |

#### 2.12.23 开启/关闭应用通知

> 需要权限：操作行为管理

**boolean setAppNotification(ComponentName admin, String packageName, int`<br>policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppNotification(ComponentName admin, String packageName, int`<br>policy) |
| 功能描述 | 开启/关闭单个应用通知（注：该接口非强管控，用户可手动修改） |
| 参数 | admin：设备管理器组件名<br>packageName：应用包名，例： `String packagePath = "com.example.packageName";`<br>policy：开启：Utils.RESTRICTION_POLICY_DEFAULT = 0 关闭：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setAppNotification(admin,packageName, policy);` |

**int getAppNotification(ComponentName admin, String packageName)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppNotification(ComponentName admin, String packageName)` |
| 功能描述 | 获取应用当前通知状态 |
| 参数 | admin：设备管理器组件名String packageName 获取通知状态应用包名，例： `String packagePath = "com.example.packageName";` |
| 返回值 | int 开启/关闭<br>开启：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>关闭：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getAppNotification(admin);` |

#### 2.12.24 开启/关闭护眼模式

> 需要权限：操作行为管理

**boolean setEyeProtectionPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setEyeProtectionPolicy(ComponentName admin, int policy)` |
| 功能描述 | 开启/关闭护眼模式（注：该接口非强管控，用户可手动修改） |
| 参数 | admin：设备管理器组件名<br>policy：开启/关闭<br>policy：开启：Utils.RESTRICTION_POLICY_DEFAULT = 0 关闭：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setEyeProtectionPolicy(admin,policy);` |

**int getEyeProtectionPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getEyeProtectionPolicy(ComponentName admin)` |
| 功能描述 | 获取当前护眼模式状态 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 开启/关闭<br>开启：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>关闭：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getEyeProtectionPolicy(admin);` |

#### 2.12.25 设置系统时间

> 需要权限：操作行为管理

**boolean setSysTime(ComponentName admin, long millis, String timeZone)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSysTime(ComponentName admin, long millis, String timeZone)` |
| 功能描述 | 设置系统时间（注：自动对时模式下不可用） |
| 参数 | admin：设备管理器组件名<br>millis：时间<br>timeZone：时区（可单独设置时间和时区，无 需设置的参数传0 或null 即可） |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setSysTime(admin, millis,timeZone);` |

#### 2.12.26 设置桌面壁纸

> 需要权限：操作行为管理

**boolean setDesktopWallpaper(ComponentName admin, Bitmap bitmap)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDesktopWallpaper(ComponentName admin, Bitmap bitmap)` |
| 功能描述 | 设置桌面壁纸 |
| 参数 | admin：设备管理器组件名<br>bitmap：壁纸资源 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setDesktopWallpaper(admin,bitmap);` |

#### 2.12.27 设置锁屏壁纸

> 需要权限：操作行为管理

**boolean setLockWallpaper(ComponentName admin, Bitmap bitmap)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setLockWallpaper(ComponentName admin, Bitmap bitmap)` |
| 功能描述 | 设置锁屏壁纸 |
| 参数 | admin：设备管理器组件名<br>bitmap：壁纸资源 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setLockWallpaper(admin, bitmap);` |

#### 2.12.28 开启/关闭阅图锁屏

> 需要权限：操作行为管理

**boolean setMagazineLockPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMagazineLockPolicy(ComponentName admin, int policy)` |
| 功能描述 | 开启/关闭阅图锁屏（注：该接口非强管控，用户可手动修改） |
| 参数 | admin：设备管理器组件名<br>policy：开启/关闭<br>policy：开启：Utils.RESTRICTION_POLICY_DEFAULT = 0 关闭：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setMagazineLockPolicy(admin,policy);` |

#### 2.12.29 允许/禁止睡眠模式

> 需要权限：操作行为管理

**boolean setSleepModePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSleepModePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止睡眠模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setSleepModePolicy(admin,policy);` |

**int getSleepModePolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getSleepModePolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取睡眠模式策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getSleepModePolicy(admin);` |

#### 2.12.30 允许/禁止WLAN 下应用自更新

> 需要权限：操作行为管理

119

**boolean setWlanAutoUpdateAppPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanAutoUpdateAppPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止WLAN 环境下应用自更新，仅针对系统应用 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setWlanAutoUpdateAppPolicy(admin, policy);` |

**int getWlanAutoUpdateAppPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanAutoUpdateAppPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取WLAN 下应用自更新策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getWlanAutoUpd(admin);` |

#### 2.12.31 允许/禁止节日壁纸

> 需要权限：操作行为管理

**boolean setHolidayWallpaperPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setHolidayWallpaperPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止节日壁纸 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setHolidayWallpaperPolicy(admin,policy);` |

**int getHolidayWallpaperPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getHolidayWallpaperPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取节日壁纸策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getHolidayWallpaperPolicy(admin);` |

#### 2.12.32 允许/禁止重置网络设置

> 需要权限：操作行为管理

**boolean setResetNetworkPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setResetNetworkPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止重置网络设置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setResetNetworkPolicy(admin,policy);` |

**int getResetNetworkPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getResetNetworkPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取重置网络设置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getResetNetworkPolicy(admin);` |

#### 2.12.33 允许/禁止还原所有设置

> 需要权限：操作行为管理

**boolean setRestoreAllSettingPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setRestoreAllSettingPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止还原所有设置 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setRestoreAllSettingPolicy(admin,policy);` |

**int getRestoreAllSettingPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getRestoreAllSettingPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取还原所有设置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getRestoreAllSettingPolicy(admin);` |

#### 2.12.34 允许/禁止省流量模式

> 需要权限：操作行为管理

**boolean setDataSavingPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setDataSavingPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止省流量模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setDataSavingPolicy(admin,policy);` |

**int getDataSavingPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getDataSavingPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取省流量模式策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getDataSavingPolicy(admin);` |

#### 2.12.35 允许/禁止文件分享

> 需要权限：操作行为管理

**boolean setFileSharePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setFileSharePolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止文件分享，仅对系统分享有效 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setFileSharePolicy(admin, policy);` |

**int getFileSharePolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getFileSharePolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取文件分享策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getFileSharePolicy(admin);` |

#### 2.12.36 打开/关闭屏幕常亮

> 需要权限：操作行为管理

124

**boolean keepSrceenOn(ComponentName admin, boolean on)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean keepSrceenOn(ComponentName admin, boolean on)`<br>(Android12 及以上支持) |
| 功能描述 | 设置打开/关闭屏幕常亮 |
| 参数 | admin：设备管理器组件名<br>on：是否常亮 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().keepSrceenOn(admin, on);` |

**boolean getSrceenOnState(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean getSrceenOnState(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取屏幕常亮策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | boolean 是否常亮 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().getSrceenOnState(admin);` |

#### 2.12.37 打开/关闭快速启动应用

> 需要权限：操作行为管理

**boolean setQuickLaunchAppPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setQuickLaunchAppPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置打开/关闭快速启动应用（全屏手势下侧滑停留快速启动应用） |
| 参数 | admin：设备管理器组件名<br>policy：打开/关闭<br>policy：打开快速启动：Utils.RESTRICTION_POLICY_ON = 5 关闭快速启动：Utils.RESTRICTION_POLICY_OFF = 6 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setQuickLaunchAppPolicy(admin,policy);` |

**int getQuickLaunchAppPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getQuickLaunchAppPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取快速启动应用策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 打开/关闭<br>打开快速启动：Utils.RESTRICTION_POLICY_ON = 5<br>关闭快速启动：Utils.RESTRICTION_POLICY_OFF = 6 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getOperationManager().getQuickLaunchAppPolicy(admin);` |

#### 2.12.38 设置系统语言

> 需要权限：操作行为管理

**boolean setSystemLanguage(ComponentName admin, Locale locale)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSystemLanguage(ComponentName admin, Locale locale)`<br>(Android12 及以上支持) |
| 功能描述 | 设置系统语言 |
| 参数 | admin：设备管理器组件名<br>locale：语言 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setSystemLanguage(admin,locale);` |

#### 2.12.39 设置系统导航模式

> 需要权限：操作行为管理

**boolean setNavigationBarMode(ComponentName admin, int mode)`<br>(Android12<br>及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setNavigationBarMode(ComponentName admin, int mode)`<br>(Android12<br>及以上支持) |
| 功能描述 | 设置系统导航模式 |
| 参数 | admin：设备管理器组件名<br>mode：导航模式<br>mode：导航键：Utils.RESTRICTION_POLICY_NAVBAR_KEY = 12 经典三段式：Utils.RESTRICTION_POLICY_NAVBAR_CLASSIC = 13 全屏：Utils.RESTRICTION_POLICY_NAVBAR_FULL_SCREEN = 14 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setNavigationBarMode(admin,mode);` |

#### 2.12.40 设置系统字体大小

> 需要权限：操作行为管理

**boolean setFontSize(ComponentName admin, float size)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setFontSize(ComponentName admin, float size)`<br>(Android12 及以上支持) |
| 功能描述 | 设置系统字体大小 |
| 参数 | admin：设备管理器组件名<br>size：字体大小，取值：小(0.8) 较小(0.9) 正常(1) 较大 (1.12) 大(1.25) |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setFontSize(admin, size);` |

#### 2.12.41 设置屏幕刷新率

> 需要权限：操作行为管理

**boolean setScreenRefreshRate(ComponentName admin, int rate)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setScreenRefreshRate(ComponentName admin, int rate)`<br>(Android12 及以上支持) |
| 功能描述 | 设置屏幕刷新率 |
| 参数 | admin：设备管理器组件名<br>rate：屏幕刷新率，高刷新率的设备支持60/90/120 等 |
| 返回值 | boolean 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getOperationManager().setScreenRefreshRate(admin,rate);` |

### 2.13 WLAN 管理类（DeviceWlanManager）

#### 2.13.1 允许/禁用/强开/关闭/开启WLAN

> 需要权限：WLAN 管理

**boolean setWlanPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用/强制开启/关闭/开启WLAN |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制打开/关闭（非强制）/开启（非强 制）<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁止：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 关闭：Utils.RESTRICTION_POLICY_ON = 5 开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanPolicy(admin, policy);` |

**int getWlanPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanPolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制打开<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁止：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2<br>关闭：Utils.RESTRICTION_POLICY_ON = 5<br>开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanPolicy(admin);` |

#### 2.13.2 WLAN 黑白名单策略

> 需要权限：WLAN 管理

**boolean setWlanBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置WLAN 黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单列表中的<br>WLAN 不可连接，白名单模式下，白名单列表之外的WLAN 不可连接 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanBlackWhitePolicy(admin,policy);` |

**int getWlanBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanBlackWhitePolicy(admin);` |

#### 2.13.3 WLAN 黑白名单列表

> 需要权限：WLAN 管理

**boolean addWlanBlackList(ComponentName admin, List<String> ssids)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addWlanBlackList(ComponentName admin, List<String> ssids)` |
| 功能描述 | 添加WLAN 黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单列表中的<br>WLAN 不可连接 |
| 参数 | admin：设备管理器组件名<br>ssids：WLAN ssid 名称列表，例： `List<String> ssids= new ArrayList<>();` `ssids.add("wifiName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().addWlanBlackList(admin, ssids);` |

**List<String> getWlanBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getWlanBlackList(ComponentName admin)` |
| 功能描述 | 获取WLAN 黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单WLAN ssid 列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getWlanManager().getWlanBlackList(admin);` |

**boolean deleteWlanBlackList(ComponentName admin, List<String> ssids)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteWlanBlackList(ComponentName admin, List<String> ssids)` |
| 功能描述 | 删除WLAN 黑名单列表 |
| 参数 | admin：设备管理器组件名<br>ssids：需删除的WLAN ssid 列表，例： `List<String> ssids= new ArrayList<>();` `ssids.add("wifiName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().deleteWlanBlackList(admin, ssids);` |

**boolean clearWlanBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearWlanBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空WLAN 黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().clearWlanBlackList(admin);` |

**boolean addWlanWhiteList(ComponentName admin, List<String> ssids)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addWlanWhiteList(ComponentName admin, List<String> ssids)` |
| 功能描述 | 添加WLAN 白名单列表，需配合黑白名单策略使用。白名单模式下，白名单列表之外<br>的WLAN 不可连接 |
| 参数 | admin：设备管理器组件名<br>ssids：WLAN ssid 名称列表，例： `List<String> ssids= new ArrayList<>();` `ssids.add("wifiName");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().addWlanWhiteList(admin, ssids);` |

**List<String> getWlanWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getWlanWhiteList(ComponentName admin)` |
| 功能描述 | 获取WLAN 白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单WLAN ssid 列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getWlanManager().getWlanWhiteList(admin);` |

**boolean deleteWlanWhiteList(ComponentName admin, List<String> ssids)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteWlanWhiteList(ComponentName admin, List<String> ssids)` |
| 功能描述 | 删除WLAN 白名单列表 |
| 参数 | admin：设备管理器组件名<br>ssids：需删除的WLAN ssid 列表，例： `List<String> ssids= new ArrayList<>();` `ssids.add("wifiName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().deleteWlanWhiteList(admin, ssids);` |

**boolean clearWlanWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearWlanWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空WLAN 白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().clearWlanWhiteList(admin);` |

#### 2.13.4 允许/禁用WLAN 热点

> 需要权限：WLAN 管理

**boolean setWlanApPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanApPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用WLAN 热点 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanApPolicy(admin, policy);` |

**int getWlanApPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanApPolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 热点策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanApPolicy(admin);` |

#### 2.13.5 WLAN 热点黑白名单策略

> 需要权限：WLAN 管理

**boolean setWlanApBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanApBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置WLAN 热点黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单列表<br>中WLAN MAC 地址的设备不可连接当前设备热点，白名单模式下，白名单列表之外<br>的WLAN MAC 地址的设备不可连接当前设备热点 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanApBlackWhitePolicy(admin,policy);` |

**int getWlanApBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanApBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 热点黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanApBlackWhitePolicy(admin);` |

#### 2.13.6 WLAN 热点黑白名单列表

> 需要权限：WLAN 管理

**boolean addWlanApBlackList(ComponentName admin, List<String> macAddrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addWlanApBlackList(ComponentName admin, List<String> macAddrs)` |
| 功能描述 | 添加WLAN 热点黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单列表<br>中WLAN MAC 地址的设备不可连接当前设备热点 |
| 参数 | admin：设备管理器组件名<br>macAddrs：设备WLAN MAC 地址列表，例： `List<String> macAddrs= new ArrayList<>();` `macAddrs.add("00:0a:95:9d:68:16");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().addWlanApBlackList(admin,macAddrs);` |

**List<String> getWlanApBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getWlanApBlackList(ComponentName admin)` |
| 功能描述 | 获取WLAN 热点黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单WLAN MAC 地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getWlanManager().getWlanApBlackList(admin);` |

**boolean deleteWlanApBlackList(ComponentName admin, List<String> macAddrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteWlanApBlackList(ComponentName admin, List<String> macAddrs)` |
| 功能描述 | 删除WLAN 热点黑名单列表 |
| 参数 | admin：设备管理器组件名<br>macAddrs：需删除的WLAN MAC 地址列表，例： `List<String> macAddrs= new ArrayList<>();` `macAddrs.add("00:0a:95:9d:68:16");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().deleteWlanApBlackList(admin,macAddrs);` |

**boolean clearWlanApBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearWlanApBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空WLAN 热点黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().clearWlanApBlackList(admin);` |

**boolean addWlanApWhiteList(ComponentName admin, List<String> macAddrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addWlanApWhiteList(ComponentName admin, List<String> macAddrs)` |
| 功能描述 | 添加WLAN 热点白名单列表，需配合黑白名单策略使用。白名单模式下，白名单列表<br>之外的WLAN MAC 地址的设备不可连接当前设备热点 |
| 参数 | admin：设备管理器组件名<br>macAddrs：设备WLAN MAC 地址列表，例： `List<String> macAddrs= new ArrayList<>();` `macAddrs.add("00:0a:95:9d:68:16");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().addWlanApWhiteList(admin,macAddrs);` |

**List<String> getWlanApWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getWlanApWhiteList(ComponentName admin)` |
| 功能描述 | 获取WLAN 热点白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单WLAN MAC 地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getWlanManager().getWlanApWhiteList(admin);` |

**boolean deleteWlanApWhiteList(ComponentName admin, List<String> macAddrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteWlanApWhiteList(ComponentName admin, List<String> macAddrs)` |
| 功能描述 | 删除WLAN 热点白名单列表 |
| 参数 | admin：设备管理器组件名<br>macAddrs：需删除的WLAN MAC 地址列表，例： `List<String> macAddrs= new ArrayList<>();` `macAddrs.add("00:0a:95:9d:68:16");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().deleteWlanApWhiteList(admin,macAddrs);` |

**boolean clearWlanApWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearWlanApWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空WLAN 热点白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().clearWlanApWhiteList(admin);` |

#### 2.13.7 允许/禁止配置WLAN

> 需要权限：WLAN 管理

**boolean setWlanConfigPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanConfigPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止配置WLAN，用户不可再修改当前WLAN 配置，已保存的WLAN 可继<br>续连接，但不可配置任何新WLAN |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanConfigPolicy(admin, policy);` |

**int getWlanConfigPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanConfigPolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 配置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanConfigPolicy(admin);` |

#### 2.13.8 添加/移除WLAN 配置

> 需要权限：WLAN 管理

137

**boolean setWlanConfigurations(ComponentName admin, List<WifiConfiguration>`<br>wifiConfigs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanConfigurations(ComponentName admin, List<WifiConfiguration>`<br>wifiConfigs) |
| 功能描述 | 添加WLAN 配置信息，并立即连接最后添加的WLAN 配置 |
| 参数 | admin：设备管理器组件名<br>wifiConfigs：WLAN 配置信息列表 |
| 返回值 | true/false 添加成功/失败（如列表中任一配置添加失败，返回false） |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanConfigurations(admin, list);` |

**List<WifiConfiguration> getWlanConfigurations(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<WifiConfiguration> getWlanConfigurations(ComponentName admin)` |
| 功能描述 | 获取WLAN 配置信息列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<WifiConfiguration> WLAN 配置信息列表 |
| 使用示例 | `List<WifiConfiguration> list = VivoEnterpriseFactory.getWlanManager().getWlanConfigurations(admin);` |

**boolean removeWlanConfigurations(ComponentName admin, int networkId)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean removeWlanConfigurations(ComponentName admin, int networkId)` |
| 功能描述 | 移除WLAN 配置信息 |
| 参数 | admin：设备管理器组件名<br>networkId：为要删除的WLAN 网络id（id 为添加时系统 自动分配，可从get 接口获取配置后从WifiConfiguration.networkId 取得） |
| 返回值 | true/false 移除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().removeWlanConfigurations(admin, id);` |

#### 2.13.9 获取WLAN MAC 地址

> 需要权限：WLAN 管理

138

**String getWifiMacAddress(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `String getWifiMacAddress(ComponentName admin)` |
| 功能描述 | 获取WLAN MAC 地址信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | `String`<br>MAC 地址 |
| 使用示例 | `String mac = VivoEnterpriseFactory.getWlanManager().getWifiMacAddress(admin);` |

#### 2.13.10 允许/禁止WLAN 直连

> 需要权限：WLAN 管理

**boolean setWlanDirectPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanDirectPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止WLAN 直连 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanDirectPolicy(admin, policy);` |

**int getWlanDirectPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanDirectPolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 直连策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanDirectPolicy(admin);` |

#### 2.13.11 允许/禁止/强开WLAN 随时扫描

> 需要权限：WLAN 管理

**boolean setWlanScanAlwaysPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanScanAlwaysPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止/强制打开WLAN 随时扫描 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强开<br>Policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁止：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanScanAlwaysPolicy(admin,policy);` |

**int getWlanScanAlwaysPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanScanAlwaysPolicy(ComponentName admin)` |
| 功能描述 | 获取WLAN 随时扫描策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强开<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁止：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanScanAlwaysPolicy(admin);` |

#### 2.13.12 允许/禁止WLAN 代理

> 需要权限：WLAN 管理

140

**boolean setWlanProxyPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setWlanProxyPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 设置允许/禁止WLAN 代理及静态IP |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getWlanManager().setWlanProxyPolicy(admin, policy);` |

**int getWlanProxyPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getWlanProxyPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取WLAN 代理策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强开<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getWlanManager().getWlanProxyPolicy(admin);` |

### 2.14 蓝牙管理类（DeviceBluetoothManager）

#### 2.14.1 允许/禁用/强开/关闭/开启蓝牙

> 需要权限：蓝牙管理

**boolean setBluetoothPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用/强制打开/关闭/开启蓝牙 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制打开/关闭（非强制）/开启（非强 制）<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 关闭：Utils.RESTRICTION_POLICY_ON = 5 开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothPolicy(admin, policy);` |

**int getBluetoothPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothPolicy(ComponentName admin)` |
| 功能描述 | 获取蓝牙策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制打开/关闭/开启<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2<br>关闭：Utils.RESTRICTION_POLICY_ON = 5<br>开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothPolicy(admin);` |

#### 2.14.2 蓝牙黑白名单策略

> 需要权限：蓝牙管理

**boolean setBluetoothBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置蓝牙黑白名单模式，配合黑白名单列表使用。黑名单模式下，黑名单列表中的蓝<br>牙地址设备不可连接，白名单模式下，白名单列表之外的蓝牙设备不可连接 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothBlackWhitePolicy(admin, policy);` |

**int getBluetoothBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取蓝牙黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothBlackWhitePolicy(admin);` |

#### 2.14.3 蓝牙黑白名单列表

> 需要权限：蓝牙管理

**boolean addBluetoothBlackList(ComponentName admin, List<String> addrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addBluetoothBlackList(ComponentName admin, List<String> addrs)` |
| 功能描述 | 添加蓝牙地址黑名单列表，需配合黑白名单策略使用。黑名单模式下，黑名单列表中<br>的蓝牙地址设备不可连接 |
| 参数 | admin：设备管理器组件名<br>addrs：蓝牙地址列表，例： `List<String> addrs= new ArrayList<>();` `addrs.add("22:22:53:A2:37:16");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().addBluetoothBlackList(admin,addrs);` |

**List<String> getBluetoothBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getBluetoothBlackList(ComponentName admin)` |
| 功能描述 | 获取蓝牙黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 黑名单蓝牙地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getBluetoothManager().getBluetoothBlackList(admin);` |

**boolean deleteBluetoothBlackList(ComponentName admin, List<String> addrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteBluetoothBlackList(ComponentName admin, List<String> addrs)` |
| 功能描述 | 删除蓝牙地址黑名单列表 |
| 参数 | admin：设备管理器组件名<br>addrs：需删除的蓝牙地址列表，例： `List<String> addrs= new ArrayList<>();` `addrs.add("22:22:53:A2:37:16");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().deleteBluetoothBlackList(admin,addrs);` |

**boolean clearBluetoothBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearBluetoothBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空蓝牙地址黑名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().clearBluetoothBlackList(admin);` |

**boolean addBluetoothWhiteList(ComponentName admin, List<String> addrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addBluetoothWhiteList(ComponentName admin, List<String> addrs)` |
| 功能描述 | 添加蓝牙地址白名单列表，需配合黑白名单策略使用。白名单模式下，白名单列表之<br>外的蓝牙地址设备不可连接 |
| 参数 | admin：设备管理器组件名<br>addrs：蓝牙地址列表，例： `List<String> addrs= new ArrayList<>();` `addrs.add("22:22:53:A2:37:16");` |
| 返回值 | true/false 添加成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().addBluetoothWhiteList(admin,addrs);` |

**List<String> getBluetoothWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getBluetoothWhiteList(ComponentName admin)` |
| 功能描述 | 获取蓝牙白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单蓝牙地址列表不存在时返回null |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getBluetoothManager().getBluetoothWhiteList(admin);` |

**boolean deleteBluetoothWhiteList(ComponentName admin, List<String> addrs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteBluetoothWhiteList(ComponentName admin, List<String> addrs)` |
| 功能描述 | 删除蓝牙地址白名单列表 |
| 参数 | admin：设备管理器组件名<br>addrs：需删除的蓝牙地址列表，例： `List<String> addrs= new ArrayList<>();` `addrs.add("22:22:53:A2:37:16");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().deleteBluetoothWhiteList(admin,addrs);` |

**boolean clearBluetoothWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearBluetoothWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空蓝牙地址白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().clearBluetoothWhiteList(admin);` |

#### 2.14.4 允许/禁用蓝牙热点

> 需要权限：蓝牙管理

**boolean setBluetoothApPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothApPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁用蓝牙热点 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothApPolicy(admin,policy);` |

**int getBluetoothApPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothApPolicy(ComponentName admin)` |
| 功能描述 | 获取蓝牙热点策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothApPolicy(admin);` |

#### 2.14.5 允许/禁止配置蓝牙

> 需要权限：蓝牙管理

**boolean setBluetoothConfigPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothConfigPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置允许/禁止配置蓝牙，用户不可再修改当前蓝牙配置，已配对的蓝牙可继续连接，<br>但不可配对任何新蓝牙 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothConfigPolicy(admin,policy);` |

**int getBluetoothConfigPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothConfigPolicy(ComponentName admin)` |
| 功能描述 | 获取蓝牙配置策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothConfigPolicy(admin);` |

#### 2.14.6 允许/禁止蓝牙分享

> 需要权限：蓝牙管理

**boolean setBluetoothSharingPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothSharingPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止使用蓝牙分享 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothSharingPolicy(admin,policy);` |

**int getBluetoothSharingPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothSharingPolicy(ComponentName admin)` |
| 功能描述 | 获取蓝牙分享策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothSharingPolicy(admin);` |

#### 2.14.7 允许/禁止蓝牙传输文件

> 需要权限：蓝牙管理

**boolean setBluetoothDataTransferPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setBluetoothDataTransferPolicy(ComponentName admin, int policy)`<br>(Android12 及以上支持) |
| 功能描述 | 允许/禁止使用蓝牙传输文件 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getBluetoothManager().setBluetoothDataTransferPolicy(admin, policy);` |

**int getBluetoothDataTransferPolicy(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getBluetoothDataTransferPolicy(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 获取蓝牙传输文件策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getBluetoothManager().getBluetoothDataTransferPolicy(admin);` |

### 2.15 USB 管理类（DeviceUsbManager）

#### 2.15.1 USB 文件传输模式

> 需要权限：USB 管理

**boolean setUsbTransferPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUsbTransferPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置USB 文件传输模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制MTP 模式/强制PTP 模式<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制MTP 模式：Utils.RESTRICTION_POLICY_USB_TRANSFER_MTP = 10 强制PTP 模式：Utils.RESTRICTION_POLICY_USB_TRANSFER_PTP = 11 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getUsbManager().setUsbTransferPolicy(admin, policy);` |

**int getUsbTransferPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUsbTransferPolicy(ComponentName admin)` |
| 功能描述 | 获取USB 文件传输模式 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制MTP 模式/强制PTP 模式<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制MTP 模式：Utils.RESTRICTION_POLICY_USB_TRANSFER_MTP = 10<br>强制PTP 模式：Utils.RESTRICTION_POLICY_USB_TRANSFER_PTP = 11 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getUsbManager().getUsbTransferPolicy(admin);` |

#### 2.15.2 允许/禁用USB 调试

> 需要权限：USB 管理

**boolean setUsbDebugPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUsbDebugPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用USB 调试（开发者模式） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getUsbManager().setUsbDebugPolicy(admin, policy);` |

**int getUsbDebugPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUsbDebugPolicy(ComponentName admin)` |
| 功能描述 | 获取USB 调试策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getUsbManager().getUsbDebugPolicy(admin);` |

#### 2.15.3 允许/禁用USB 热点

> 需要权限：USB 管理

**boolean setUsbApPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUsbApPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用USB 热点 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getUsbManager().setUsbApPolicy(admin, policy);` |

**int getUsbApPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUsbApPolicy(ComponentName admin)` |
| 功能描述 | 获取USB 热点策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getUsbManager().getUsbApPolicy(admin);` |

#### 2.15.4 允许/禁用OTG

> 需要权限：USB 管理

**boolean setOtgPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setOtgPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用OTG |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getUsbManager().setOtgPolicy(admin, policy);` |

**int getOtgPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getOtgPolicy(ComponentName admin)` |
| 功能描述 | 获取OTG 策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getUsbManager().getOtgPolicy(admin);` |

### 2.16 外设管理类（DevicePeripheralManager）

#### 2.16.1 允许/禁用/强开/关闭/开启定位服务

> 需要权限：定位管理

152

**boolean setAppLocationPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAppLocationPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用/强制打开/关闭/开启定位服务 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制打开/关闭（非强制）/开启（非强 制）<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 关闭：Utils.RESTRICTION_POLICY_ON = 5 开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setAppLocationPolicy(admin,policy);` |

**int getAppLocationPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAppLocationPolicy(ComponentName admin)` |
| 功能描述 | 获取定位服务策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制打开/关闭/开启<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2<br>关闭：Utils.RESTRICTION_POLICY_ON = 5<br>开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getAppLocationPolicy(admin);` |

#### 2.16.2 允许/禁用相机

> 需要权限：相机管理

**boolean setCameraPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setCameraPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止相机权限 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setCameraPolicy(admin, policy);` |

**int getCameraPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getCameraPolicy(ComponentName admin)` |
| 功能描述 | 获取相机权限策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getCameraPolicy(admin);` |

#### 2.16.3 允许/禁用闪光灯

> 需要权限：相机管理

**boolean setFlashPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setFlashPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用闪光灯 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setFlashPolicy(admin, policy);` |

**int getFlashPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getFlashPolicy(ComponentName admin)` |
| 功能描述 | 获取闪光灯策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getFlashPolicy(admin);` |

#### 2.16.4 允许/禁用麦克风录音

> 需要权限：麦克风管理

**boolean setMicRecordPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMicRecordPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用麦克风录音 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setMicRecordPolicy(admin,policy);` |

**int getMicRecordPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMicRecordPolicy(ComponentName admin)` |
| 功能描述 | 获取麦克风录音策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getMicRecordPolicy(admin);` |

#### 2.16.5 允许/禁用SD 卡

> 需要权限：外部存储管理

**boolean setExternalStoragePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setExternalStoragePolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止SD 卡挂载（如果设置前已插入SD 卡，则设备重启才可生效） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setExternalStoragePolicy(admin,policy);` |

**int getExternalStoragePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getExternalStoragePolicy(ComponentName admin)` |
| 功能描述 | 获取SD 卡策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getExternalStoragePolicy(admin);` |

#### 2.16.6 允许/禁用NFC 传输

> 需要权限：NFC 管理

156

**boolean setNfcSharingPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setNfcSharingPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用NFC 传输数据（仅禁止NFC 数据传输功能） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setNfcSharingPolicy(admin,policy);` |

**int getNfcSharingPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getNfcSharingPolicy(ComponentName admin)` |
| 功能描述 | 获取NFC 传输策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getNfcSharingPolicy(admin);` |

#### 2.16.7 允许/禁用/强开NFC

> 需要权限：NFC 管理

**boolean setNfcPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setNfcPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用NFC（禁止NFC 所有功能）/强开 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/强制打开<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getPeripheralManager().setNfcPolicy(admin, policy);` |

**int getNfcPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getNfcPolicy(ComponentName admin)` |
| 功能描述 | 获取NFC 管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止/强制打开<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>强制打开：Utils.RESTRICTION_POLICY_FORCE_TURN_ON = 2 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getPeripheralManager().getNfcPolicy(admin);` |

### 2.17 通话管理类（DeviceCallManager）

#### 2.17.1 通话限制

> 需要权限：通话管理

**boolean setPhoneCallSimPolicy(ComponentName admin, int simId, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPhoneCallSimPolicy(ComponentName admin, int simId, int policy)` |
| 功能描述 | 设置SIM 卡通话管控策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003<br>policy：限制呼入或呼出 不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000 限制呼出：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 限制呼入：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setPhoneCallSimPolicy(admin, simId,policy);` |

**int getPhoneCallSimPolicy(ComponentName admin, int simId)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPhoneCallSimPolicy(ComponentName admin, int simId)` |
| 功能描述 | 获取SIM 卡通话策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要获取管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003 |
| 返回值 | int<br>限制策略<br>不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000<br>限制呼出：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010<br>限制呼入：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020<br>全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getCallManager().getPhoneCallSimPolicy(admin, simId);` |

#### 2.17.2 通话黑白名单策略

> 需要权限：通话管理

**boolean setCallBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setCallBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置通话黑白名单策略，配合黑白名单列表使用，在黑名单模式下，黑名单中的号码<br>被限制通话，白名单模式下，白名单之外的号码被限制通话 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setCallBlackWhitePolicy(admin, policy);` |

**int getCallBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getCallBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取通话黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getCallManager().getCallBlackWhitePolicy(admin);` |

#### 2.17.3 通话黑白名单列表

> 需要权限：通话管理

**boolean addCallBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addCallBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 添加通话黑名单列表信息，配合黑白名单策略使用，在黑名单模式下，黑名单中的号<br>码被限制通话，具体限制方式由numInfos 参数决定 |
| 参数 | admin：设备管理器组件名<br>numInfos：限制策略（详细参考TelecomNumRestrictionInfo 类） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().addCallBlackList(admin, numInfos);` |

**List<TelecomNumRestrictionInfo> getCallBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<TelecomNumRestrictionInfo> getCallBlackList(ComponentName admin)` |
| 功能描述 | 获取通话黑名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<TelecomNumRestrictionInfo> 黑名单列表信息（详细参考<br>TelecomNumRestrictionInfo 类） |
| 使用示例 | `List<TelecomNumRestrictionInfo> list = VivoEnterpriseFactory.getCallManager().getCallBlackList(admin);` |

**boolean deleteCallBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteCallBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 删除通话黑名单列表信息 |
| 参数 | admin：设备管理器组件名<br>numInfos：需删除黑名单列表信息 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().deleteCallBlackList(admin, numInfos);` |

**boolean clearCallBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearCallBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空通话黑名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().clearCallBlackList(admin);` |

**boolean addCallWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addCallWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 添加通话白名单列表信息，配合黑白名单策略使用，在白名单模式下，白名单之外的<br>号码被限制通话，具体限制方式由numInfos 参数决定 |
| 参数 | admin：设备管理器组件名<br>numInfos：限制策略（详细参考TelecomNumRestrictionInfo 类） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().addCallWhiteList(admin, numInfos);` |

**List<TelecomNumRestrictionInfo> getCallWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<TelecomNumRestrictionInfo> getCallWhiteList(ComponentName admin)` |
| 功能描述 | 获取通话白名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<TelecomNumRestrictionInfo> 白名单列表信息（详细参考<br>TelecomNumRestrictionInfo 类） |
| 使用示例 | `List<TelecomNumRestrictionInfo> list = VivoEnterpriseFactory.getCallManager().getCallWhiteList(admin);` |

**boolean deleteCallWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteCallWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 删除通话白名单列表信息 |
| 参数 | admin：设备管理器组件名<br>numInfos：需删除白名单列表信息 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().deleteCallWhiteList(admin, numInfos);` |

**boolean clearCallWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearCallWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空通话白名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().clearCallWhiteList(admin);` |

#### 2.17.4 允许/禁用通话录音

> 需要权限：通话管理

**boolean setCallRecordPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setCallRecordPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置用户手动通话录音管控策略 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setCallRecordPolicy(admin, policy);` |

**int getCallRecordPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getCallRecordPolicy(ComponentName admin)` |
| 功能描述 | 获取通话录音管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getCallManager().getCallRecordPolicy(admin);` |

#### 2.17.5 允许/禁用三方通话

> 需要权限：通话管理

**boolean setMutliCallPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMutliCallPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止三方通话 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setMutliCallPolicy(admin, policy);` |

**int getMutliCallPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMutliCallPolicy(ComponentName admin)` |
| 功能描述 | 获取三方通话管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getCallManager().getMutliCallPolicy(admin);` |

#### 2.17.6 通话次数限制

> 需要权限：通话管理

**boolean setPhoneCallLimit(ComponentName admin, int inOrOut, int count)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPhoneCallLimit(ComponentName admin, int inOrOut, int count)` |
| 功能描述 | 限制通话次数，次数消耗完后禁止通话（未接通不计入消耗次数） |
| 参数 | admin：设备管理器组件名<br>inOrOut：呼入或呼出限制 呼出：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 呼入：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 呼出呼入：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030<br>count：次数（传入-1 时清除限制） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setPhoneCallLimit(admin, inOrOut,count);` |

**int getPhoneCallLimit(ComponentName admin, int inOrOut)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPhoneCallLimit(ComponentName admin, int inOrOut)` |
| 功能描述 | 获取剩余通话次数 |
| 参数 | admin：设备管理器组件名<br>inOrOut：呼入或呼出限制 呼出：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 呼入：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 呼出呼入：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 返回值 | int<br>剩余呼入或呼出次数 |
| 使用示例 | `int count = VivoEnterpriseFactory.getCallManager().getPhoneCallLimit(admin, inOrOut);` |

#### 2.17.7 允许/禁用呼叫转移

> 需要权限：通话管理

**boolean setForwardCallPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setForwardCallPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止呼叫转移 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getCallManager().setForwardCallPolicy(admin, policy);` |

**int getForwardCallPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getForwardCallPolicy(ComponentName admin)` |
| 功能描述 | 获取呼叫转移管控策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int count = VivoEnterpriseFactory.getCallManager().getForwardCallPolicy(admin);` |

### 2.18 短信管理类（DeviceSmsManager）

#### 2.18.1 短信限制

> 需要权限：信息管理

**boolean setPhoneSmsSimPolicy(ComponentName admin, int simId, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPhoneSmsSimPolicy(ComponentName admin, int simId, int policy)` |
| 功能描述 | 设置SIM 卡短信管控策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003<br>policy：限制发送或接收 不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000 限制发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 限制接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().setPhoneSmsSimPolicy(admin, simId,policy);` |

**int getPhoneSmsSimPolicy(ComponentName admin, int simId)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPhoneSmsSimPolicy(ComponentName admin, int simId)` |
| 功能描述 | 获取SIM 卡短信策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要获取管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003 |
| 返回值 | int<br>限制策略<br>不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000<br>限制发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010<br>限制接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020<br>全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getSmsManager().getPhoneSmsSimPolicy(admin, simId);` |

#### 2.18.2 短信黑白名单策略

> 需要权限：信息管理

**boolean setSmsBlackWhitePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSmsBlackWhitePolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置短信黑白名单策略，配合黑白名单列表使用，在黑名单模式下，黑名单中的号码<br>被限制短信，白名单模式下，白名单之外的号码被限制短信 |
| 参数 | admin：设备管理器组件名<br>policy：默认/黑名单模式/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().setSmsBlackWhitePolicy(admin,policy);` |

**int getSmsBlackWhitePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getSmsBlackWhitePolicy(ComponentName admin)` |
| 功能描述 | 获取短信黑白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 默认/黑名单模式/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>黑名单模式：Utils.RESTRICTION_POLICY_BLACKLIST = 3<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getSmsManager().getSmsBlackWhitePolicy(admin);` |

#### 2.18.3 短信黑白名单列表

> 需要权限：信息管理

**boolean addSmsBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addSmsBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 添加短信黑名单列表信息，配合黑白名单策略使用，在黑名单模式下，黑名单中的号<br>码被限制短信，具体限制方式由numInfos 参数决定 |
| 参数 | admin：设备管理器组件名<br>numInfos：限制策略（详细参考TelecomNumRestrictionInfo 类） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().addSmsBlackList(admin, numInfos);` |

**List<TelecomNumRestrictionInfo> getSmsBlackList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<TelecomNumRestrictionInfo> getSmsBlackList(ComponentName admin)` |
| 功能描述 | 获取短信黑名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<TelecomNumRestrictionInfo> 黑名单列表信息（详细参考<br>TelecomNumRestrictionInfo 类） |
| 使用示例 | `List<TelecomNumRestrictionInfo> list = VivoEnterpriseFactory.getSmsManager().getSmsBlackList(admin);` |

**boolean deleteSmsBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteSmsBlackList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 删除短信黑名单列表信息 |
| 参数 | admin：设备管理器组件名<br>numInfos：需删除黑名单列表信息 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().deleteSmsBlackList(admin, numInfos);` |

**boolean clearSmsBlackList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearSmsBlackList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空短信黑名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().clearSmsBlackList(admin);` |

**boolean addSmsWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addSmsWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 添加短信白名单列表信息，配合黑白名单策略使用，在白名单模式下，白名单之外的<br>号码被限制短信，具体限制方式由numInfos 参数决定 |
| 参数 | admin：设备管理器组件名<br>numInfos：限制策略（详细参考TelecomNumRestrictionInfo 类） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().addSmsWhiteList(admin, numInfos);` |

**List<TelecomNumRestrictionInfo> getSmsWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<TelecomNumRestrictionInfo> getSmsWhiteList(ComponentName admin)` |
| 功能描述 | 获取短信白名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<TelecomNumRestrictionInfo> 白名单列表信息（详细参考<br>TelecomNumRestrictionInfo 类） |
| 使用示例 | `List<TelecomNumRestrictionInfo> list = VivoEnterpriseFactory.getSmsManager().getSmsWhiteList(admin);` |

**boolean deleteSmsWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteSmsWhiteList(ComponentName admin,List<TelecomNumRestrictionInfo> numInfos)` |
| 功能描述 | 删除短信白名单列表信息 |
| 参数 | admin：设备管理器组件名<br>numInfos：需删除白名单列表信息 |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().deleteSmsWhiteList(admin, numInfos);` |

**boolean clearSmsWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearSmsWhiteList(ComponentName admin)` |
| 功能描述 | 清空短信白名单列表信息 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().clearSmsWhiteList(admin);` |

#### 2.18.4 彩信限制

> 需要权限：信息管理

**boolean setPhoneMmsSimPolicy(ComponentName admin, int simId, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPhoneMmsSimPolicy(ComponentName admin, int simId, int policy)` |
| 功能描述 | 设置SIM 卡彩信管控策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003<br>policy：限制发送或接收 不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000 限制发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 限制接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().setPhoneMmsSimPolicy(admin, simId,policy);` |

**int getPhoneMmsSimPolicy(ComponentName admin, int simId)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPhoneMmsSimPolicy(ComponentName admin, int simId)` |
| 功能描述 | 获取SIM 卡彩信策略 |
| 参数 | admin：设备管理器组件名<br>simId：需要获取管控的sim 卡<br>SIM：卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>SIM：卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003 |
| 返回值 | int<br>限制策略<br>不限制：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000<br>限制发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010<br>限制接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020<br>全限制：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 使用示例 | `int policy = VivoEnterpriseFactory.getSmsManager().getPhoneMmsSimPolicy(admin, simId);` |

#### 2.18.5 短信次数限制

> 需要权限：信息管理

**boolean setPhoneSmsLimit(ComponentName admin, int inOrOut, int count)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPhoneSmsLimit(ComponentName admin, int inOrOut, int count)` |
| 功能描述 | 限制短信次数，次数消耗完后禁止收发短信 |
| 参数 | admin：设备管理器组件名<br>inOrOut：接收或发送限制 发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 发送接收：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030<br>count：次数（传入-1 时清除限制） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSmsManager().setPhoneSmsLimit(admin, inOrOut,count);` |

**int getPhoneSmsLimit(ComponentName admin, int inOrOut)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPhoneSmsLimit(ComponentName admin, int inOrOut)` |
| 功能描述 | 获取剩余短信次数 |
| 参数 | admin：设备管理器组件名<br>inOrOut：接收或发送限制 发送：Utils.POLICY_TELECOM_FLAG_OUT = 0x00000010 接收：Utils.POLICY_TELECOM_FLAG_IN = 0x00000020 发送接收：Utils.POLICY_TELECOM_FLAG_IN_OUT = 0x00000030 |
| 返回值 | int<br>剩余接收或发送次数 |
| 使用示例 | `int count = VivoEnterpriseFactory.getSmsManager().getPhoneSmsLimit(admin, inOrOut);` |

### 2.19 通信管理类（DeviceTelecomManager）

#### 2.19.1 允许/禁用/打开/关闭飞行模式

> 需要权限：通信状态管理

**boolean setAirplaneModePolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setAirplaneModePolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用/开启/关闭飞行模式，禁用后，用户无法手动开启飞行模式 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止/关闭（非强制）/开启（非强制）<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 关闭：Utils.RESTRICTION_POLICY_ON = 5 开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().setAirplaneModePolicy(admin,policy);` |

**int getAirplaneModePolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getAirplaneModePolicy(ComponentName admin)` |
| 功能描述 | 获取飞行模式策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁止/关闭（非强制）/开启（非强制）<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>关闭：Utils.RESTRICTION_POLICY_ON = 5<br>开启：Utils.RESTRICTION_POLICY_OFF = 6 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getTelecomManager().getAirplaneModePolicy(admin);` |

#### 2.19.2 允许/禁用SIM 卡槽

> 需要权限：通信状态管理

**boolean setSimSlotPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setSimSlotPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁用SIM 卡槽，禁用后SIM 卡槽不可用 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁用卡1/禁用卡2/禁用所有卡<br>Policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000 禁用卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001 禁用卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002 禁用所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().setSimSlotPolicy(admin, policy);` |

**int getSimSlotPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getSimSlotPolicy(ComponentName admin)` |
| 功能描述 | 获取卡槽禁用策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁用卡1/禁用卡2/禁用所有卡<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0x00000000<br>禁用卡1：Utils.POLICY_TELECOM_FLAG_SIM1 = 0x00000001<br>禁用卡2：Utils.POLICY_TELECOM_FLAG_SIM2 = 0x00000002<br>禁用所有卡：Utils.POLICY_TELECOM_FLAG_SIM_ALL = 0x00000003 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getTelecomManager().getSimSlotPolicy(admin);` |

#### 2.19.3 获取SIM 卡号码

可使用系统原生接口获取，如需特殊权限，在申请证书时填入即可。

#### 2.19.4 获取SIM 卡ICCID

可使用系统原生接口获取，如需特殊权限，在申请证书时填入即可。

#### 2.19.5 获取设备IMEI

可使用系统原生接口获取，如需特殊权限，在申请证书时填入即可。

#### 2.19.6 挂断电话

> 需要权限：通话管理

**boolean endCall(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean endCall(ComponentName admin)` |
| 功能描述 | 挂断当前通话 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 挂断成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().endCall(admin);` |

#### 2.19.7 接听电话

> 需要权限：通话管理

**boolean answerCall(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean answerCall(ComponentName admin)` |
| 功能描述 | 接听当前来电 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 接通成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().answerCall(admin);` |

#### 2.19.8 开启/关闭电话号码脱敏

> 需要权限：通信状态管理

**boolean setMaskPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMaskPolicy(ComponentName admin, int policy)` |
| 功能描述 | 开启/关闭电话号码脱敏，开启脱敏后，联系人、通话记录、短信、拨号盘等界面会隐<br>藏电话号码，号码中间几位用*号代替 |
| 参数 | admin：设备管理器组件名<br>policy：开启/关闭脱敏<br>Policy：开启脱敏：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 关闭脱敏：Utils.RESTRICTION_POLICY_DEFAULT = 0 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().setMaskPolicy(admin, policy);` |

**int getMaskPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMaskPolicy(ComponentName admin)` |
| 功能描述 | 获取电话号码脱敏策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>开启/关闭脱敏<br>开启脱敏：Utils.RESTRICTION_POLICY_FORBIDDEN = 1<br>关闭脱敏：Utils.RESTRICTION_POLICY_DEFAULT = 0 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getTelecomManager().getMaskPolicy(admin);` |

#### 2.19.9 通信权限白名单策略

> 需要权限：通信状态管理

176

**boolean setMaskPermissionPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setMaskPermissionPolicy(ComponentName admin, int policy)` |
| 功能描述 | 设置通信权限白名单策略，配合白名单列表使用，在白名单模式下，白名单列表之外<br>的应用无法获得读取通话记录、读取联系人、读取信息权限（注：使用<br>addAppPermissionWhiteList 接口加入系统权限白名单的应用默认拥有以上权限，无<br>需额外再添加）<br>主要配合号码脱敏管控使用，使其他三方应用无法取得联系人号码 |
| 参数 | admin：设备管理器组件名<br>policy：默认/白名单模式<br>policy：默认：Utils.RESTRICTION_POLICY_DEFAULT = 0 白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().setMaskPermissionPolicy(admin,policy);` |

**int getMaskPermissionPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getMaskPermissionPolicy(ComponentName admin)` |
| 功能描述 | 获取通信权限白名单策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>默认/白名单模式<br>默认：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>白名单模式：Utils.RESTRICTION_POLICY_WHITELIST = 4 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getTelecomManager().getMaskPermissionPolicy(admin);` |

#### 2.19.10 通信权限白名单列表

> 需要权限：通信状态管理

**boolean addAppMaskPermissionWhiteList(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean addAppMaskPermissionWhiteList(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 添加通信权限白名单列表（读取通话记录、联系人、信息权限），配合白名单策略使<br>用，在白名单模式下，白名单列表之外的应用无法获得读取通话记录、读取联系人、<br>读取信息权限 |
| 参数 | admin：设备管理器组件名<br>pkgs：应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().addAppMaskPermissionWhiteList(admin, pkgs);` |

**List<String> getAppMaskPermissionWhiteList(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `List<String> getAppMaskPermissionWhiteList(ComponentName admin)` |
| 功能描述 | 获取通信权限白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | List<String> 白名单应用包名列表 |
| 使用示例 | `List<String> list = VivoEnterpriseFactory.getTelecomManager().getAppMaskPermissionWhiteList(admin);` |

**boolean deleteAppMaskPermissionWhiteList(ComponentName admin, List<String>`<br>pkgs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean deleteAppMaskPermissionWhiteList(ComponentName admin, List<String>`<br>pkgs) |
| 功能描述 | 删除通信权限白名单列表 |
| 参数 | admin：设备管理器组件名<br>pkgs：需删除白名单应用包名列表，例： `List<String> pkgs= new ArrayList<>();` `pkgs.add("com.example.packageName");` |
| 返回值 | true/false 删除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().deleteAppMaskPermissionWhiteList(admin, pkgs);` |

**boolean clearAppMaskPermissionWhiteList(ComponentName admin)`<br>(Android12 及以上支持)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearAppMaskPermissionWhiteList(ComponentName admin)`<br>(Android12 及以上支持) |
| 功能描述 | 清空通信权限白名单列表 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清空成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().clearAppMaskPermissionWhiteList(admin);` |

#### 2.19.11 允许/禁用PIN 码锁

> 需要权限：通信状态管理

**boolean setPinLockPolicy(ComponentName admin, String password, Stringpassword2, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setPinLockPolicy(ComponentName admin, String password, Stringpassword2, int policy)` |
| 功能描述 | 允许/禁用SIM 卡PIN 码锁，如果用户已设置PIN 码锁，需要传入正确的PIN 码才可<br>禁用 |
| 参数 | admin：设备管理器组件名<br>password：卡1 的PIN 码<br>password2：卡2 的PIN 码（无PIN 码时传null 即可）<br>policy：允许/禁用 允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 2 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getTelecomManager().setPinLockPolicy(admin, password,password2, policy);` |

**int getPinLockPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getPinLockPolicy(ComponentName admin)` |
| 功能描述 | 获取SIM 卡PIN 码锁策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁用<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 2 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getTelecomManager().getPinLockPolicy(admin);` |

### 2.20 安全管理类（DeviceSecurityManager）

#### 2.20.1 获取设备ROOT 状态

> 需要权限：安全状态管理

**boolean isDeviceRoot(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean isDeviceRoot(ComponentName admin)` |
| 功能描述 | 获取设备当前root 状态 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 已root/未root |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().isDeviceRoot(admin);` |

#### 2.20.2 立即锁定

> 需要权限：锁屏和密码管理

**void lockNow(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void lockNow(ComponentName admin)` |
| 功能描述 | 立即锁定屏幕 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getSecurityManager().lockNow(admin);` |

#### 2.20.3 重置锁屏密码

> 需要权限：锁屏和密码管理

**boolean setResetPasswordToken(ComponentName admin, byte[] token)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setResetPasswordToken(ComponentName admin, byte[] token)` |
| 功能描述 | 设置可重置锁屏密码的token，这个token 相当于重置密码的一把钥匙，与<br>resetPasswordWithToken 配合使用，设置后必须在用户锁屏一次后才可激活生效，否<br>则调用resetPasswordWithToken 时会抛出异常<br>注：设置token 时必须保证为新设备，从未被用户设置过锁屏密码，否则可能无法设<br>置token 成功，如设备支持找回密码，请调用setForgotPasswordPolicy 禁用找回密<br>码 |
| 参数 | admin：设备管理器组件名<br>token：安全验证token（自定义，长度至少为32） |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().setResetPasswordToken(admin,token);` |

**boolean clearResetPasswordToken(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean clearResetPasswordToken(ComponentName admin)` |
| 功能描述 | 清除可重置锁屏密码的token |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 清除成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().clearResetPasswordToken(admin);` |

**boolean isResetPasswordTokenActive(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean isResetPasswordTokenActive(ComponentName admin)` |
| 功能描述 | 获取当前可重置锁屏密码的token 是否为激活状态，处于激活状态时才可调用<br>resetPasswordWithToken 接口重置设备密码 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | true/false 已激活/未激活 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().isResetPasswordTokenActive(admin);` |

**boolean resetPasswordWithToken(ComponentName admin, String password, byte[] token, int flags)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean resetPasswordWithToken(ComponentName admin, String password, byte[] token, int flags)` |
| 功能描述 | 使用之前设置的token 去修改锁屏密码（注意勿设置系统不支持的密码字符） |
| 参数 | admin：设备管理器组件名<br>password：新密码（为空则清除之前的密码）<br>token：之前设置的token<br>flags：0 默认只修改密码1 不允许其他设备管理器修改密码直到用户手动修改2 重 启开机不需要再输入密码确认 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().resetPasswordWithToken(admin,password, token, flags);` |

#### 2.20.4 自动锁屏时间

> 需要权限：锁屏和密码管理

**void setMaximumTimeToLock(ComponentName admin, long timeMs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setMaximumTimeToLock(ComponentName admin, long timeMs)` |
| 功能描述 | 设置自动锁屏时间，时间值必须低于系统自动锁屏时间，设置后用户手动修改无效 |
| 参数 | admin：设备管理器组件名<br>timeMs：自动锁屏时间（单位ms，设置为0 则恢复为系 统自动锁屏时间） |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getSecurityManager().setMaximumTimeToLock(admin, timeMs);` |

**long getMaximumTimeToLock(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `long getMaximumTimeToLock(ComponentName admin)` |
| 功能描述 | 获取自动锁屏时间 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | long 锁屏时间 |
| 使用示例 | `long timeMs = VivoEnterpriseFactory.getSecurityManager().getMaximumTimeToLock(admin);` |

#### 2.20.5 锁屏强认证超时时间

> 需要权限：锁屏和密码管理

**void setRequiredStrongAuthTimeout(ComponentName admin, long timeoutMs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setRequiredStrongAuthTimeout(ComponentName admin, long timeoutMs)` |
| 功能描述 | 设置锁屏强认证超时时间，即使用强认证解锁（密码、图案）后，每次超过设定的时<br>间需要再次通过强认证方式才能解锁（此时使用人脸、指纹、虹膜等方式解锁无效），<br>最短设置1 个小时，最长72 小时 |
| 参数 | admin：设备管理器组件名<br>timeMs：超时时间（单位ms）为0 则不限制 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getSecurityManager().setRequiredStrongAuthTimeout(admin, timeoutMs);` |

**long getRequiredStrongAuthTimeout(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `long getRequiredStrongAuthTimeout(ComponentName admin)` |
| 功能描述 | 获取强认证锁屏超时时间 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | long 强认证超时时间 |
| 使用示例 | `long timeMs = VivoEnterpriseFactory.getSecurityManager().getRequiredStrongAuthTimeout(admin);` |

#### 2.20.6 密码过期时间

183

> 需要权限：锁屏和密码管理

**void setPasswordExpirationTimeout(ComponentName admin, long timeoutMs)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setPasswordExpirationTimeout(ComponentName admin, long timeoutMs)` |
| 功能描述 | 设置密码过期时间（过期时间到后发出广播<br>android.app.action.ACTION_PASSWORD_EXPIRING，该广播必须由设备管理器<br>receiver 组件接收，收到广播后由APP 自行处理锁定手机或其他操作） |
| 参数 | admin：设备管理器组件名<br>timeMs：过期时间，为0 则不限制（单位ms） |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getSecurityManager().getRequiredStrongAuthTimeout(admin);` |

**long getPasswordExpirationTimeout(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `long getPasswordExpirationTimeout(ComponentName admin)` |
| 功能描述 | 获取密码过期时间 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | long 密码过期时间 |
| 使用示例 | `long timeMs = VivoEnterpriseFactory.getSecurityManager().getPasswordExpirationTimeout(admin);` |

#### 2.20.7 锁屏功能限制

> 需要权限：锁屏和密码管理

**void setKeyguardDisabledFeatures(ComponentName admin, int flag)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `void setKeyguardDisabledFeatures(ComponentName admin, int flag)` |
| 功能描述 | 设置锁屏功能限制特性 |
| 参数 | admin：设备管理器组件名<br>flag：锁屏限制： 0：不限制 2：禁止锁屏相机 32：禁止指纹解锁 128：禁止人脸解锁 0x7fffffff：同时禁止以上所有 |
| 返回值 | 无 |
| 使用示例 | `VivoEnterpriseFactory.getSecurityManager().setKeyguardDisabledFeatures(admin, flag);` |

**int getKeyguardDisabledFeatures(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getKeyguardDisabledFeatures(ComponentName admin)` |
| 功能描述 | 获取锁屏功能限制策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 限制策略值 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getSecurityManager().getKeyguardDisabledFeatures(admin);` |

#### 2.20.8 允许/禁止找回密码

> 需要权限：锁屏和密码管理

**boolean setForgotPasswordPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setForgotPasswordPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止找回密码，忘记密码后在锁屏界面不显示找回密码按钮 |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 设置成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getSecurityManager().setForgotPasswordPolicy(admin,policy);` |

**int getForgotPasswordPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getForgotPasswordPolicy(ComponentName admin)` |
| 功能描述 | 获取找回密码策略 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int 允许/禁止<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getSecurityManager().getForgotPasswordPolicy(admin);` |

### 2.21 用户管理类（DeviceUserManager）

#### 2.21.1 允许/禁止创建多用户

> 需要权限：用户管理

**boolean setUserAddPolicy(ComponentName admin, int policy)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `boolean setUserAddPolicy(ComponentName admin, int policy)` |
| 功能描述 | 允许/禁止创建多用户（防止多用户下各类管控失效） |
| 参数 | admin：设备管理器组件名<br>policy：允许/禁止<br>policy：允许：Utils.RESTRICTION_POLICY_DEFAULT = 0 禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 返回值 | true/false 成功/失败 |
| 使用示例 | `boolean result = VivoEnterpriseFactory.getUserManager().setUserAddPolicy(admin, policy);` |

**int getUserAddPolicy(ComponentName admin)**

| 项目 | 说明 |
| --- | --- |
| 接口名 | `int getUserAddPolicy(ComponentName admin)` |
| 功能描述 | 获取多用户管控状态 |
| 参数 | admin：设备管理器组件名 |
| 返回值 | int<br>允许/禁用<br>允许：Utils.RESTRICTION_POLICY_DEFAULT = 0<br>禁用：Utils.RESTRICTION_POLICY_FORBIDDEN = 1 |
| 使用示例 | `int policy= VivoEnterpriseFactory.getUserManager().getUserAddPolicy(admin);` |

## 3 其他功能类及参数定义

### 3.1 管控策略值定义类（Utils）

| 策略字段名 | 值 | 含义 |
| --- | --- | --- |
| RESTRICTION_POLICY_DEFAULT | 0 | 默认（不做管控）/允许 |
| RESTRICTION_POLICY_FORBIDDEN | 1 | 禁止/禁用 |
| RESTRICTION_POLICY_FORCE_TURN_ON | 2 | 强制开启 |
| RESTRICTION_POLICY_BLACKLIST | 3 | 黑名单模式 |
| RESTRICTION_POLICY_WHITELIST | 4 | 白名单模式 |
| RESTRICTION_POLICY_ON | 5 | 打开（非强制） |
| RESTRICTION_POLICY_OFF | 6 | 关闭（非强制） |
| RESTRICTION_POLICY_USB_TRANSFER_MTP | 10 | USB 传输强制MTP 模式 |
| RESTRICTION_POLICY_USB_TRANSFER_PTP | 11 | USB 传输强制PTP 模式 |
| RESTRICTION_POLICY_NAVBAR_KEY | 12 | 导航方式：导航键 |
| RESTRICTION_POLICY_NAVBAR_CLASSIC | 13 | 导航方式：经典三段式 |
| RESTRICTION_POLICY_NAVBAR_FULL_SCREEN | 187 | 导航方式：全屏手势 |
| RESTRICTION_POLICY_WHITELIST_TWO | 15 | 白名单模式2 |
| PERMISSION_POLICY_PROMPT | 0 | 运行时权限策略：询问用户 |
| PERMISSION_POLICY_AUTO_GRANT | 1 | 运行时权限策略：自动允许 |
| PERMISSION_POLICY_AUTO_DENY | 2 | 运行时权限策略：自动拒绝 |
| POLICY_TELECOM_FLAG_SIM1 | 0x00000001 | 通信管控策略：卡1 |
| POLICY_TELECOM_FLAG_SIM2 | 0x00000002 | 通信管控策略：卡2 |
| POLICY_TELECOM_FLAG_SIM_ALL | 0x00000003 | 通信管控策略：所有卡 |
| POLICY_TELECOM_FLAG_OUT | 0x00000010 | 通信管控策略：呼出（发送） |
| POLICY_TELECOM_FLAG_IN | 0x00000020 | 通信管控策略：呼入（接收） |
| POLICY_TELECOM_FLAG_IN_OUT | 0x00000030 | 通信管控策略：呼出呼入（发<br>送接收） |
| ACTION_VIVO_EMM_VOLUMEUP_LONGPRESS | 见SDK | 长按音量上键action |
| ACTION_VIVO_EMM_JOVIKEY_LONGPRESS | 见SDK | 长按AI 键action |

### 3.2 VPN 配置类（CustVpnProfile）

添加VPN 配置信息，各字段含义对应源码VpnProfile 类

### 3.3 通信管控黑白名单信息类（TelecomNumRestrictionInfo）

针对指定号码管控，需配合黑白名单策略使用

num：需要管控的号码

simID：设置需要限制的SIM 卡，见Utils 类SIM 卡相关字段

inAndOut：设置需要限制的呼出呼入（发送接收）状态，见Utils 类相关字段

188

以设置通话黑白名单为例：

若处于黑名单模式下，添加黑名单时TelecomNumRestrictionInfo 字段如下配置

num 为18812345678，simID 为Utils. POLICY_TELECOM_FLAG_SIM1，inAndOut 为Utils.

POLICY_TELECOM_FLAG_OUT

表示禁止SIM 卡1 拨打号码18812345678

若处于白名单模式下，添加白名单时TelecomNumRestrictionInfo 字段如下配置

num 为18812345678，simID 为Utils. POLICY_TELECOM_FLAG_SIM1，inAndOut 为Utils.

POLICY_TELECOM_FLAG_OUT

表示只允许SIM 卡1 拨打号码18812345678，其他号码都不允许拨打

### 3.4 通话状态

可在证书申请系统权限使用系统原生监听或广播方式。

vivo 还提供其他方式获取通话状态，可根据需求结合使用，通过监听通话状态可自行实现通话

录音等需求。

#### 3.4.1 vivo 通话状态监听

比源生系统监听提供更多的通话状态信息。

通话状态改变时，应用需要从传递过来的Bundle 参数中根据不同字段名解析获取通话信息。

字段说明：

bundle (Bundle)：保存所有信息的Bundle

callState (int)：0—无通话；1—通话中；2—保持通话中；3—新去电；5—新来电；7—挂断

callHandle (string)：正在通话的对方号码

slotId (int)：当前通话使用的SIM 卡，0—SIM 卡1；1—SIM 卡2

age (int)：通话时长，挂断时获取，单位：秒

代码示例：

先定义Listener 类：

189

```java
private static class VivoPhoneStateListener extends CustPhoneStateListener {
@Override
public void onVivoCustCallStateChanged (Bundle data) {//vivo 监听回调if (data != null) {
int state = data.getInt("callState");
String number = data.getString("callHandle");
int slotid = data.getInt("slotId");
int time = data.getInt("age");
switch (state){
case CustPhoneStateListener.PRECISE_CALL_STATE_IDLE:
case CustPhoneStateListener.PRECISE_CALL_STATE_DISCONNECTED:....}
}
}
}
//启动监听：
VivoPhoneStateListener mListener = new VivoPhoneStateListener();
mListener.addListener();
//结束监听：
mListener. removeListener();
```

#### 3.4.2 vivo 通话广播

通过注册监听广播“vivo.app.action.EMM_PRECISE_CALL_STATE_CHANGE”获取通话状态时，需要

额外在AndroidManifest.xml 文件加上vivo 自定义权限的声明<permission

android:name="com.vivo.enterprise.permission.EMM" android:protectionLevel="normal"/>，广播

消息可能会有延时，请谨慎用于通话录音等对时效性要求较高的需求。

通话状态改变时，应用需要从广播传递过来的Intent 中先获取Bundle 对象，然后在Bundle 中

根据不同字段名获取信息。

字段说明：同vivo 通话状态监听

例：

收到广播后从intent 参数获取信息

```java
Bundle bundle = new Bundle();
bundle = intent.getBundleExtra("bundle");
int state = bundle.getInt("callState");
String number = bundle.getString("callHandle");
190
int slotid = bundle.getInt("slotId");
int time = bundle.getInt("age");
```

#### 3.4.3 原生通话状态监听

支持系统原生通话监听，实现方式自行查询，如需特殊系统权限，可在申请证书时将权限字段

填入系统权限一栏。

#### 3.4.4 通话录音

根据录音方式不同可能需要在证书申请android.permission.CAPTURE_AUDIO_OUTPUT 等系统权

限，以实现双向录音等需求，请自行查阅Android 官方文档通话录音方式。

Android 11.0 以后，Google 禁止后台服务使用定位、相机、录音等操作，如有需要请使用前

台服务。参考https://developer.android.google.cn/guide/components/foreground-services

注：通话录音时建议禁用三方通话功能，防止通话状态混乱。

