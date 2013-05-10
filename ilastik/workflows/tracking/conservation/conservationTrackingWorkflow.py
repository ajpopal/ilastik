from lazyflow.graph import Graph
from ilastik.workflow import Workflow
from ilastik.applets.dataSelection import DataSelectionApplet
from ilastik.applets.tracking.conservation.conservationTrackingApplet import ConservationTrackingApplet
from ilastik.applets.objectClassification.objectClassificationApplet import ObjectClassificationApplet
from ilastik.applets.opticalTranslation.opticalTranslationApplet import OpticalTranslationApplet
from ilastik.applets.thresholdTwoLevels.thresholdTwoLevelsApplet import ThresholdTwoLevelsApplet
from lazyflow.operators.adaptors import Op5ifyer
from ilastik.applets.trackingFeatureExtraction.trackingFeatureExtractionApplet import TrackingFeatureExtractionApplet
from ilastik.applets.objectExtraction import config

class ConservationTrackingWorkflow( Workflow ):
    workflowName = "Tracking Workflow (Conservation Tracking)"

    def __init__( self, headless, *args, **kwargs ):
        graph = kwargs['graph'] if 'graph' in kwargs else Graph()
        if 'graph' in kwargs: del kwargs['graph']
        super(ConservationTrackingWorkflow, self).__init__(headless=headless, graph=graph, *args, **kwargs)
        
        ## Create applets 
        self.dataSelectionApplet = DataSelectionApplet(self, 
                                                       "Input Data", 
                                                       "Input Data", 
                                                       batchDataGui=False,
                                                       force5d=False)
        
        opDataSelection = self.dataSelectionApplet.topLevelOperator
        opDataSelection.DatasetRoles.setValue( ['Raw Data', 'Prediction Maps'] )
                
        self.thresholdTwoLevelsApplet = ThresholdTwoLevelsApplet( self, 
                                                                  "Threshold & Size Filter", 
                                                                  "ThresholdTwoLevels" )        
        
        self.opticalTranslationApplet = OpticalTranslationApplet(workflow=self)
                                                                   
        self.objectExtractionApplet = TrackingFeatureExtractionApplet(workflow=self,
                                                                      name="Object Extraction")                                                                      
        
        self.divisionDetectionApplet = ObjectClassificationApplet(workflow=self,
                                                                     name="Division Detection",
                                                                     projectFileGroupName="DivisionDetection")
        
        self.cellClassificationApplet = ObjectClassificationApplet(workflow=self,
                                                                     name="Cell Classification",
                                                                     projectFileGroupName="CellClassification")
                
        self.trackingApplet = ConservationTrackingApplet( workflow=self )
        
        self._applets = []                
        self._applets.append(self.dataSelectionApplet)
        self._applets.append(self.thresholdTwoLevelsApplet)
        self._applets.append(self.opticalTranslationApplet)
        self._applets.append(self.objectExtractionApplet)
        self._applets.append(self.divisionDetectionApplet)
        self._applets.append(self.cellClassificationApplet)
        self._applets.append(self.trackingApplet)
        
    @property
    def applets(self):
        return self._applets
    
    @property
    def imageNameListSlot(self):
        return self.dataSelectionApplet.topLevelOperator.ImageName
    
    def connectLane(self, laneIndex):
        opData = self.dataSelectionApplet.topLevelOperator.getLane(laneIndex)
        opTwoLevelThreshold = self.thresholdTwoLevelsApplet.topLevelOperator.getLane(laneIndex)
        opOptTranslation = self.opticalTranslationApplet.topLevelOperator.getLane(laneIndex)
        opObjExtraction = self.objectExtractionApplet.topLevelOperator.getLane(laneIndex)    
        opDivDetection = self.divisionDetectionApplet.topLevelOperator.getLane(laneIndex)
        opCellClassification = self.cellClassificationApplet.topLevelOperator.getLane(laneIndex)
        opTracking = self.trackingApplet.topLevelOperator.getLane(laneIndex)
        
        op5Raw = Op5ifyer(parent=self)
        op5Raw.input.connect(opData.ImageGroup[0])
        
        op5Predictions = Op5ifyer( parent=self )
        op5Predictions.input.connect( opData.ImageGroup[1] )
               
        opTwoLevelThreshold.InputImage.connect( opData.ImageGroup[1] )
        opTwoLevelThreshold.RawInput.connect( opData.ImageGroup[0] ) # Used for display only
        opTwoLevelThreshold.Channel.setValue(1)
        
        # Use Op5ifyers for both input datasets such that they are guaranteed to 
        # have the same axis order after thresholding
        op5Binary = Op5ifyer( parent=self )                
        op5Binary.input.connect( opTwoLevelThreshold.CachedOutput )
        
        opOptTranslation.RawImage.connect( op5Raw.output )
        opOptTranslation.BinaryImage.connect( op5Binary.output )
        
        ## Connect operators ##        
        features = {}
        features[config.features_vigra_name] = { name: {} for name in config.vigra_features }                
        opObjExtraction.RawImage.connect( op5Raw.output )
        opObjExtraction.BinaryImage.connect( op5Binary.output )
        opObjExtraction.TranslationVectors.connect( opOptTranslation.TranslationVectors )
        opObjExtraction.Features.setValue(features)        
        
        
        selected_features_div = {}
        for plugin_name in config.selected_features_division_detection.keys():
            selected_features_div[plugin_name] = { name: {} for name in config.selected_features_division_detection[plugin_name] }
        opDivDetection.BinaryImages.connect( op5Binary.output )
        opDivDetection.RawImages.connect( op5Raw.output )        
        opDivDetection.LabelsAllowedFlags.connect(opData.AllowLabels)
        opDivDetection.SegmentationImages.connect(opObjExtraction.LabelImage)
        opDivDetection.ObjectFeatures.connect(opObjExtraction.RegionFeatures)
        opDivDetection.ComputedFeatureNames.connect(opObjExtraction.ComputedFeatureNames)
        opDivDetection.SelectedFeatures.setValue(selected_features_div)
        
        selected_features_cell = {}
        for plugin_name in config.selected_features_cell_classification.keys():
            selected_features_cell[plugin_name] = { name: {} for name in config.selected_features_cell_classification[plugin_name] }
        opCellClassification.BinaryImages.connect( op5Binary.output )
        opCellClassification.RawImages.connect( op5Raw.output )
        opCellClassification.LabelsAllowedFlags.connect(opData.AllowLabels)
        opCellClassification.SegmentationImages.connect(opObjExtraction.LabelImage)
        opCellClassification.ObjectFeatures.connect(opObjExtraction.RegionFeatures)
        opCellClassification.ComputedFeatureNames.connect(opObjExtraction.ComputedFeatureNames)
        opCellClassification.SelectedFeatures.setValue( selected_features_cell )
        
        opTracking.RawImage.connect( op5Raw.output )
        opTracking.LabelImage.connect( opObjExtraction.LabelImage )
        opTracking.ObjectFeatures.connect( opDivDetection.ObjectFeatures )
        opTracking.DivisionProbabilities.connect( opDivDetection.Probabilities )
        opTracking.DetectionProbabilities.connect( opCellClassification.Probabilities )        
#        opTracking.RegionLocalCenters.connect( opObjExtraction.RegionLocalCenters )        
    
