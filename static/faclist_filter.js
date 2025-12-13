/**
 * Faclist级联筛选器公共逻辑
 * 用于统一管理Faclist筛选器的行为和状态
 */

(function() {
    'use strict';
    
    // 存储正在进行的请求，用于去重和取消
    const pendingRequests = new Map();
    // 存储已初始化的前缀，避免重复初始化
    const initializedPrefixes = new Set();
    // 防抖定时器
    const debounceTimers = new Map();
    
    /**
     * 更新Faclist筛选器选项（级联更新）
     * @param {string} prefix - ID前缀
     * @param {string} excludeField - 要排除的字段名（用于focus事件，排除当前字段）
     * @param {string} onlyUpdateField - 只更新指定字段的选项（用于focus事件，只更新当前字段）
     */
    function updateFaclistOptions(prefix, excludeField, onlyUpdateField) {
        prefix = prefix || '';
        const baseUrl = window.location.pathname;

        // 获取当前选择的值
        const subproject = document.getElementById(`${prefix}faclistSubproject`)?.value || '';
        const train = document.getElementById(`${prefix}faclistTrain`)?.value || '';
        const unit = document.getElementById(`${prefix}faclistUnit`)?.value || '';
        const simpleblk = document.getElementById(`${prefix}faclistSimpleBLK`)?.value || '';
        const mainblockVal = document.getElementById(`${prefix}faclistMainBlock`)?.value || '';
        const blockVal = document.getElementById(`${prefix}faclistBlock`)?.value || '';
        const bccquarterVal = document.getElementById(`${prefix}faclistBCCQuarter`)?.value || '';

        // 根据页面确定API URL
        let apiUrl = '/api/dashboard/faclist_options';
        if (baseUrl.includes('/systems')) {
            apiUrl = '/api/faclist_options';  // 系统管理使用 /api/faclist_options
        } else if (baseUrl.includes('/subsystems')) {
            apiUrl = '/subsystems/api/faclist_options';  // 子系统管理使用 /subsystems/api/faclist_options
        } else if (baseUrl.includes('/precom')) {
            apiUrl = '/api/precom/faclist_options';
        } else if (baseUrl.includes('/test_packages') || baseUrl.includes('/test-packages')) {
            apiUrl = '/api/faclist_options';  // 试压包管理使用 /api/faclist_options
        }

        // 所有维度都参与互相约束：任何一个非空条件都会作为过滤条件传给后端
        // 构造查询参数：默认所有维度都参与过滤
        const params = {
            subproject_code: subproject,
            train,
            unit,
            simpleblk,
            mainblock: mainblockVal,
            block: blockVal,
            bccquarter: bccquarterVal
        };

        // 如果指定了要"忽略自身"的字段，则将该字段置为空，从过滤条件中移除
        if (excludeField && Object.prototype.hasOwnProperty.call(params, excludeField)) {
            params[excludeField] = '';
        }

        const qs = new URLSearchParams(params).toString();
        const requestKey = `${prefix}_${qs}`;

        // 如果已经有相同的请求正在进行，取消它
        if (pendingRequests.has(requestKey)) {
            const controller = pendingRequests.get(requestKey);
            if (controller && controller.abort) {
                controller.abort();
            }
        }

        // 创建新的 AbortController 用于取消请求
        const controller = new AbortController();
        pendingRequests.set(requestKey, controller);

        fetch(`${apiUrl}?${qs}`, { signal: controller.signal })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                // 请求完成后移除
                pendingRequests.delete(requestKey);
                
                if (!data || data.success === false) return;

                // 帮助函数：更新下拉框选项，尽量保留当前值
                function renderOptions(selectId, options, placeholder, current) {
                    const sel = document.getElementById(selectId);
                    if (!sel || !options) return;
                    const prev = current || sel.value || '';
                    sel.innerHTML = '';
                    const opt = document.createElement('option');
                    opt.value = '';
                    opt.textContent = placeholder;
                    sel.appendChild(opt);
                    options.forEach(v => {
                        const o = document.createElement('option');
                        o.value = v;
                        o.textContent = v;
                        if (v === prev) o.selected = true;
                        sel.appendChild(o);
                    });
                    // 如果之前的值不在新选项里，则保持为空
                    if (prev && !options.includes(prev)) {
                        sel.value = '';
                    }
                }

                // 如果指定了只更新某个字段，则只更新该字段，其他字段保持不变
                if (onlyUpdateField) {
                    // 字段名映射
                    const fieldMap = {
                        'subproject_code': () => renderOptions(`${prefix}faclistSubproject`, data.subproject_codes || [], '全部 SubProject', subproject),
                        'train': () => renderOptions(`${prefix}faclistTrain`, data.trains || [], '全部 Train', train),
                        'unit': () => renderOptions(`${prefix}faclistUnit`, data.units || [], '全部装置', unit),
                        'simpleblk': () => renderOptions(`${prefix}faclistSimpleBLK`, data.simpleblks || [], '全部大主项', simpleblk),
                        'mainblock': () => {
                            let mainblockOptions = [];
                            if (simpleblk && data.mainblocks && data.mainblocks[simpleblk]) {
                                mainblockOptions = data.mainblocks[simpleblk].slice().sort();
                            } else if (data.mainblocks) {
                                const set = new Set();
                                Object.values(data.mainblocks).forEach(arr => arr.forEach(v => set.add(v)));
                                mainblockOptions = Array.from(set).sort();
                            }
                            renderOptions(`${prefix}faclistMainBlock`, mainblockOptions, '全部主项', mainblockVal);
                        },
                        'block': () => {
                            let blockOptions = [];
                            const blockMap = data.blocks || {};
                            if (mainblockVal && blockMap[mainblockVal]) {
                                blockOptions = blockMap[mainblockVal].slice().sort();
                            } else {
                                const setB = new Set();
                                Object.values(blockMap).forEach(arr => arr.forEach(v => setB.add(v)));
                                blockOptions = Array.from(setB).sort();
                            }
                            renderOptions(`${prefix}faclistBlock`, blockOptions, '全部CIA主子项', blockVal);
                        },
                        'bccquarter': () => renderOptions(`${prefix}faclistBCCQuarter`, data.bccquarters || [], '全部片区', bccquarterVal)
                    };
                    
                    // 只更新指定字段
                    if (fieldMap[onlyUpdateField]) {
                        fieldMap[onlyUpdateField]();
                    }
                    return; // 只更新一个字段后直接返回
                }

                // 否则更新所有字段（change事件）
                // SubProject
                renderOptions(`${prefix}faclistSubproject`, data.subproject_codes || [], '全部 SubProject', subproject);
                // Train
                renderOptions(`${prefix}faclistTrain`, data.trains || [], '全部 Train', train);
                // Unit
                renderOptions(`${prefix}faclistUnit`, data.units || [], '全部装置', unit);
                // SimpleBLK
                renderOptions(`${prefix}faclistSimpleBLK`, data.simpleblks || [], '全部大主项', simpleblk);

                // MainBlock：根据当前SimpleBLK过滤，否则用全部
                let mainblockOptions = [];
                if (simpleblk && data.mainblocks && data.mainblocks[simpleblk]) {
                    mainblockOptions = data.mainblocks[simpleblk].slice().sort();
                } else if (data.mainblocks) {
                    const set = new Set();
                    Object.values(data.mainblocks).forEach(arr => arr.forEach(v => set.add(v)));
                    mainblockOptions = Array.from(set).sort();
                }
                renderOptions(`${prefix}faclistMainBlock`, mainblockOptions, '全部主项', mainblockVal);

                // Block：根据当前MainBlock过滤，否则用全部
                let blockOptions = [];
                const blockMap = data.blocks || {};
                if (mainblockVal && blockMap[mainblockVal]) {
                    blockOptions = blockMap[mainblockVal].slice().sort();
                } else {
                    const setB = new Set();
                    Object.values(blockMap).forEach(arr => arr.forEach(v => setB.add(v)));
                    blockOptions = Array.from(setB).sort();
                }
                renderOptions(`${prefix}faclistBlock`, blockOptions, '全部CIA主子项', blockVal);

                // BCCQuarter
                renderOptions(`${prefix}faclistBCCQuarter`, data.bccquarters || [], '全部片区', bccquarterVal);
            })
            .catch(err => {
                // 请求完成后移除
                pendingRequests.delete(requestKey);
                // 忽略 AbortError（请求被取消）
                if (err.name !== 'AbortError') {
                    console.error('更新Faclist选项失败', err);
                }
            });
    }
    
    /**
     * 切换Faclist筛选器的显示/隐藏
     * @param {string} prefix - ID前缀
     */
    function toggleFaclistFilter(prefix) {
        prefix = prefix || '';
        const faclistFilter = document.getElementById(`${prefix}faclistFilter`);
        if (faclistFilter) {
            const isCurrentlyHidden = faclistFilter.style.display === 'none' || !faclistFilter.style.display;
            
            if (isCurrentlyHidden) {
                // 展开筛选器
                faclistFilter.style.display = 'block';
                
                // 检查是否已经有值（从URL加载的）
                const hasExistingValues = Array.from(faclistFilter.querySelectorAll('select')).some(s => s.value !== '');
                
                // 只有在没有现有值时才重置（避免清空用户正在使用的筛选条件）
                if (!hasExistingValues) {
                    resetFaclistFilter(prefix, false);
                }
            } else {
                // 隐藏筛选器（不重置值，用户可能只是想暂时隐藏）
                faclistFilter.style.display = 'none';
            }
        }
    }
    
    /**
     * 重置Faclist筛选器（不影响搜索结果）
     * @param {string} prefix - ID前缀
     * @param {boolean} hideFilter - 是否隐藏筛选器
     */
    function resetFaclistFilter(prefix, hideFilter) {
        prefix = prefix || '';
        hideFilter = hideFilter !== false; // 默认为true
        
        // 重置所有select到"全部"
        const selects = [
            `${prefix}faclistSubproject`,
            `${prefix}faclistTrain`,
            `${prefix}faclistUnit`,
            `${prefix}faclistSimpleBLK`,
            `${prefix}faclistMainBlock`,
            `${prefix}faclistBlock`,
            `${prefix}faclistBCCQuarter`
        ];
        
        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                select.value = '';
            }
        });
        
        // 如果需要，隐藏筛选器
        if (hideFilter) {
            const faclistFilter = document.getElementById(`${prefix}faclistFilter`);
            if (faclistFilter) {
                faclistFilter.style.display = 'none';
            }
        }
    }
    
    /**
     * 防抖函数
     */
    function debounce(func, wait, key) {
        return function(...args) {
            if (debounceTimers.has(key)) {
                clearTimeout(debounceTimers.get(key));
            }
            const timer = setTimeout(() => {
                func.apply(this, args);
                debounceTimers.delete(key);
            }, wait);
            debounceTimers.set(key, timer);
        };
    }
    
    /**
     * 初始化Faclist筛选器（避免重复初始化）
     */
    function initFaclistFilter() {
        // 为所有Faclist下拉框绑定change事件，动态级联
        document.querySelectorAll('[id$="faclistFilter"]').forEach(function(filter) {
            const prefix = filter.id.replace('faclistFilter', '');
            
            // 如果已经初始化过，跳过（避免重复绑定事件）
            if (initializedPrefixes.has(prefix)) {
                return;
            }
            
            const selects = filter.querySelectorAll('select');
            selects.forEach(sel => {
                // 获取字段名映射
                const name = sel.getAttribute('name') || '';
                let excludeField = '';
                if (name === 'subproject_code') excludeField = 'subproject_code';
                else if (name === 'train') excludeField = 'train';
                else if (name === 'unit') excludeField = 'unit';
                else if (name === 'simpleblk') excludeField = 'simpleblk';
                else if (name === 'mainblock') excludeField = 'mainblock';
                else if (name === 'block') excludeField = 'block';
                else if (name === 'bccquarter') excludeField = 'bccquarter';

                // 创建防抖函数（每个字段独立防抖）
                const debouncedFocusUpdate = debounce(function() {
                    // 如果当前字段有值，则更新选项（排除当前字段），但只更新当前字段的选项
                    // 这样用户可以看到所有可选项，而不被当前值限制，同时不影响其他字段
                    if (sel.value && excludeField) {
                        updateFaclistOptions(prefix, excludeField, name); // 传入当前字段名，只更新该字段
                    }
                }, 200, `${prefix}_focus_${name}`);

                const debouncedChangeUpdate = debounce(function() {
                    // 不传 excludeField，这样当前字段的新值会参与过滤，影响所有下游字段
                    updateFaclistOptions(prefix);
                }, 300, `${prefix}_change_${name}`);

                // 当用户点击下拉框时，如果当前字段有值，先更新选项（排除当前字段）
                // 这样用户可以看到所有可选项，而不被当前值限制
                sel.addEventListener('focus', debouncedFocusUpdate, { passive: true });

                // 当值改变时，更新所有下游字段的选项（不排除当前字段，使用新值来过滤）
                sel.addEventListener('change', debouncedChangeUpdate, { passive: true });
            });
            
            // 标记为已初始化
            initializedPrefixes.add(prefix);
        });
        
        if (initializedPrefixes.size > 0) {
            console.log('Faclist筛选器已初始化 - 级联启用', Array.from(initializedPrefixes));
        }
    }
    
    /**
     * 重置初始化状态（用于页面动态更新后重新初始化）
     */
    function resetInitialization(prefix) {
        if (prefix) {
            initializedPrefixes.delete(prefix);
        } else {
            initializedPrefixes.clear();
        }
    }
    
    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFaclistFilter);
    } else {
        initFaclistFilter();
    }
    
    // 导出全局函数
    window.toggleFaclistFilter = toggleFaclistFilter;
    window.resetFaclistFilter = resetFaclistFilter;
    window.updateFaclistOptions = updateFaclistOptions;
    window.resetFaclistInitialization = resetInitialization;
    
    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFaclistFilter);
    } else {
        initFaclistFilter();
    }
    
    // 监听 DOM 变化，如果页面动态添加了新的 Faclist 筛选器，自动初始化
    const observer = new MutationObserver(function(mutations) {
        let shouldReinit = false;
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length > 0) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) { // Element node
                        if (node.id && node.id.endsWith('faclistFilter')) {
                            shouldReinit = true;
                        } else if (node.querySelectorAll && node.querySelectorAll('[id$="faclistFilter"]').length > 0) {
                            shouldReinit = true;
                        }
                    }
                });
            }
        });
        if (shouldReinit) {
            // 延迟一点，确保 DOM 完全更新
            setTimeout(initFaclistFilter, 100);
        }
    });
    
    // 开始观察 DOM 变化
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    // 调试信息
    console.log('Faclist筛选器脚本已加载', {
        toggleFaclistFilter: typeof window.toggleFaclistFilter,
        resetFaclistFilter: typeof window.resetFaclistFilter,
        updateFaclistOptions: typeof window.updateFaclistOptions,
        resetFaclistInitialization: typeof window.resetFaclistInitialization
    });
})();

