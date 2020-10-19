import React from 'react';
import { Button, Col, Row } from 'react-bootstrap';
import FormCard from './FormCard';
import RadioGroup from './Atoms/RadioGroup';
import Input from './Atoms/Input';

const SignalForm = ({formik, handlePageChange}) => 
    <React.Fragment>
        <Row>
            <Col>
                <FormCard title="Signal">
                    <Row>
                        <Col>
                            <RadioGroup 
                                formik={formik} 
                                title="Injection" 
                                name="signalChoice" 
                                options={[
                                    {label: 'Binary Black Hole', value: 'binaryBlackHole'}, 
                                    {label: 'Binary Neutron Star', value: 'binaryNeutronStar'}
                                ]}/>
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <Row>
            <Col>
                <FormCard title="Injected Signal Parameters">
                    <Row>
                        <Col>
                            <Input formik={formik} title="Mass 1 (M&#9737;)" name="mass1" type="number" />
                        </Col>
                        <Col>
                            <Input formik={formik} title="Mass 2 (M&#9737;)" name="mass2" type="number" />
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Input 
                                formik={formik} 
                                title="Luminosity distance (Mpc)" 
                                name="luminosityDistance" 
                                type="number" />
                        </Col>
                        <Col>
                            <Input formik={formik} title="Merger time (GPS)" name="mergerTime" type="number" />
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Input formik={formik} title="psi" name="psi" type="number" />
                        </Col>
                        <Col>
                            <Input formik={formik} title="iota" name="iota" type="number" />
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Input formik={formik} title="Phase" name="phase" type="number" />
                        </Col>
                        <Col />
                    </Row>
                    <Row>
                        <Col>
                            <Input formik={formik} title="Right ascension (radians)" name="ra" type="number" />
                        </Col>
                        <Col>
                            <Input formik={formik} title="Declination (degrees)" name="dec" type="number" />
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <Row>
            <Col>
                <Button onClick={() => handlePageChange('priorsAndSampler')}>Save and continue</Button>
            </Col>
        </Row>
    </React.Fragment>;

export default SignalForm;
